#!/usr/bin/env python3
"""
auto_analisar_litispendencia.py — Executa a fila de análise de litispendência
via Claude Code (claude -p).

Compatível com Claude Code 2.1.x:
  - Usa --dangerously-skip-permissions para destravar Write/Edit em modo -p.
    (--permission-mode bypassPermissions sozinho não basta em algumas
    configurações, incluindo projetos sob OneDrive no Windows.)
  - Prompt como argumento de `-p` (não via stdin)
  - --max-turns para limitar custo
  - --add-dir <projeto> para garantir acesso de I/O
  - Cria pastas de resultado antes de rodar
  - Detecta rate limit ("You've hit your limit · resets Xpm") e espera reset
  - Granularidade por GRUPO via controle_grupos.json (fonte da verdade)
  - Salva progresso por CMD via checkpoint.json
  - Retomada automática a partir do último CMD concluído
  - Verificação pós-CMD: confere que os grupos esperados foram salvos

Uso:
    python auto_analisar_litispendencia.py                # todos pendentes
    python auto_analisar_litispendencia.py --max 10       # 10 CMDs
    python auto_analisar_litispendencia.py --de 5 --ate 20
    python auto_analisar_litispendencia.py --dry          # preview
    python auto_analisar_litispendencia.py --consolidar   # gera planilha ao final
    python auto_analisar_litispendencia.py --verbose      # saída em tempo real

Segurança:
    --dangerously-skip-permissions desativa TODAS as confirmações de uso
    de ferramentas (Read/Write/Edit/Bash) dentro deste subprocesso. O
    Claude Code só age sobre o diretório do projeto (--add-dir). Use só
    em diretório confiável que você controla.
"""

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
SERVICE_DIR = ROOT / "services" / "litispendencia"
FILA_PATH = SERVICE_DIR / "fila.json"
CMDS_PATH = SERVICE_DIR / "comandos_claude_code.txt"
CHECKPOINT_PATH = SERVICE_DIR / "checkpoint.json"
CONTROLE_PATH = SERVICE_DIR / "controle_grupos.json"
GRUPOS_DIR = SERVICE_DIR / "resultados" / "grupos"
LOG_DIR = SERVICE_DIR / "logs"

IS_WINDOWS = platform.system() == "Windows"
TZ_FORTALEZA = ZoneInfo("America/Fortaleza")

# ── Localização do executável do Claude Code ────────────────────────

def _find_claude():
    """Encontra o executável do Claude Code, incluindo .cmd no Windows."""
    p = shutil.which("claude")
    if p:
        return p
    if IS_WINDOWS:
        p = shutil.which("claude.cmd")
        if p:
            return p
    return None


def verificar_claude_code():
    """Verifica se o Claude Code está instalado e acessível."""
    claude_path = _find_claude()
    if not claude_path:
        print("\n  ✗ Claude Code não encontrado no PATH.")
        print("    Instale: npm install -g @anthropic-ai/claude-code")
        print("    Depois: claude login")
        sys.exit(1)

    try:
        if IS_WINDOWS and claude_path.lower().endswith((".cmd", ".bat")):
            cmd = ["cmd.exe", "/D", "/S", "/C", claude_path, "--version"]
        else:
            cmd = [claude_path, "--version"]
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=10,
        )
        version = result.stdout.strip() or result.stderr.strip()
        print(f"  ✓ Claude Code: {version} ({claude_path})")
    except Exception:
        print(f"  ✓ Claude Code em: {claude_path} (versão não detectada)")

    return claude_path


# ── Detecção de rate limit ──────────────────────────────────────────

RE_RATE_LIMIT = re.compile(
    r"hit\s+your\s+limit.*?resets?\s+(\d{1,2})(:\d{2})?\s*(am|pm)",
    re.IGNORECASE | re.DOTALL,
)


def detectar_rate_limit(output: str) -> tuple[bool, datetime | None]:
    """Detecta mensagem de rate limit. Retorna (detectado, hora_reset)."""
    if not output:
        return False, None

    m = RE_RATE_LIMIT.search(output)
    if not m:
        return False, None

    hora = int(m.group(1))
    minuto = int(m.group(2)[1:]) if m.group(2) else 0
    periodo = m.group(3).lower()

    if periodo == "pm" and hora != 12:
        hora += 12
    elif periodo == "am" and hora == 12:
        hora = 0

    agora = datetime.now(TZ_FORTALEZA)
    reset = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if reset <= agora:
        reset += timedelta(days=1)

    return True, reset


def esperar_rate_limit(reset: datetime, verbose: bool = False):
    """Dorme até a hora de reset + margem de 30s."""
    margem = timedelta(seconds=30)
    alvo = reset + margem

    while True:
        agora = datetime.now(TZ_FORTALEZA)
        if agora >= alvo:
            break
        restante = alvo - agora
        mins = int(restante.total_seconds() // 60)
        secs = int(restante.total_seconds() % 60)

        if verbose or mins % 5 == 0:
            print(f"  ⏳ Rate limit: aguardando {mins:02d}m{secs:02d}s "
                  f"até {alvo.strftime('%H:%M:%S')} (Fortaleza)")

        time.sleep(min(60, restante.total_seconds()))


# ── Carga de estado ─────────────────────────────────────────────────

def carregar_fila():
    if not FILA_PATH.exists():
        print(f"\n  ✗ Fila não encontrada: {FILA_PATH}")
        print(f"     Rode: python run.py litispendencia fila\n")
        sys.exit(1)
    return json.loads(FILA_PATH.read_text(encoding="utf-8"))


def carregar_checkpoint():
    if CHECKPOINT_PATH.exists():
        try:
            return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "criado_em": datetime.now().isoformat(),
        "ultima_atualizacao": "",
        "processos_analisados": {},
        "comandos_concluidos": [],
        "ultimo_comando": 0,
        "sessoes": [],
        "erros_por_cmd": {},
    }


def salvar_checkpoint(ck):
    ck["ultima_atualizacao"] = datetime.now().isoformat()
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(
        json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def carregar_controle():
    if CONTROLE_PATH.exists():
        try:
            return json.loads(CONTROLE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"atualizado_em": "", "total_analisados": 0, "grupos": {}}


# ── Extração de comandos do .txt ────────────────────────────────────

def extrair_textos_cmds(cmds_path: Path) -> dict[int, str]:
    """Lê comandos_claude_code.txt e retorna {num_cmd: texto_completo}."""
    if not cmds_path.exists():
        return {}

    conteudo = cmds_path.read_text(encoding="utf-8")
    blocos = re.split(r"(?=^# === CMD \d{3})", conteudo, flags=re.MULTILINE)
    out = {}
    for bloco in blocos:
        m = re.search(r"^# === CMD (\d{3})", bloco)
        if m:
            out[int(m.group(1))] = bloco.strip()
    return out


# ── Verificação pós-CMD ─────────────────────────────────────────────

def verificar_grupos_do_cmd(group_ids: list[str]) -> tuple[list[str], list[str]]:
    """Para cada group_id, verifica se o arquivo JSON foi gerado e é válido.

    Retorna (feitos, faltantes).
    """
    feitos, faltantes = [], []
    controle = carregar_controle()
    grupos_no_controle = set(controle.get("grupos", {}).keys())

    for gid in group_ids:
        arq = GRUPOS_DIR / f"grupo_{gid}.json"
        ok_arquivo = False
        if arq.exists():
            try:
                dados = json.loads(arq.read_text(encoding="utf-8"))
                if all(k in dados for k in ("group_id", "classificacao_final", "confianca", "prioridade")):
                    ok_arquivo = True
            except json.JSONDecodeError:
                pass

        if ok_arquivo or gid in grupos_no_controle:
            feitos.append(gid)
        else:
            faltantes.append(gid)

    return feitos, faltantes


# ── Execução de um CMD ──────────────────────────────────────────────

def _montar_invocacao(claude_path: str) -> list[str]:
    """Monta a lista de argumentos do subprocess para invocar o Claude Code.

    Windows + claude.CMD: subprocess sem shell=True não consegue executar
    .cmd/.bat diretamente (WinError 193). Solução: invocar via
    `cmd.exe /D /S /C "<caminho>" ...`. Como o prompt vai pelo stdin
    (não como argumento), o cmd.exe não tem chance de reinterpretar
    caracteres especiais do prompt.

    Linux/Mac: subprocess executa o binário direto, sem shell.
    """
    base = [
        "-p",
        "--dangerously-skip-permissions",
        "--add-dir", str(ROOT),
        "--max-turns", "60",
        "--output-format", "text",
    ]
    if IS_WINDOWS and claude_path.lower().endswith((".cmd", ".bat")):
        # /D ignora AutoRun, /S preserva o quoting do primeiro arg
        return ["cmd.exe", "/D", "/S", "/C", claude_path, *base]
    return [claude_path, *base]


def executar_cmd(num_cmd: int, texto: str, claude_path: str,
                 timeout: int, verbose: bool) -> tuple[bool, str, str]:
    """Executa um CMD via `claude -p` lendo o prompt do STDIN.

    Por que stdin e não argumento de `-p`:
        No Windows, quando subprocess passa argumentos para `claude.CMD`,
        o cmd.exe (wrapper de batch) reaparseia a linha e interpreta
        caracteres do prompt (`|`, `&`, `<`, `>`, `(`, `)`, `%`, `^`)
        como operadores do shell. Isso quebra o argumento e derruba as
        flags que vêm depois, incluindo --dangerously-skip-permissions.
        O prompt deste service tem tabelas com `|` e paths — propenso
        a quebrar.

        Solução robusta: passar o prompt via STDIN. O Claude Code aceita
        isso quando `-p` é usado sem valor ("useful for pipes" no help).
        Stdin não passa pelo cmd.exe, então o prompt chega íntegro.

    Flags importantes para Claude Code 2.1.x:
      - --dangerously-skip-permissions: desliga TODAS as confirmações
        de tool. Requer a opção "Permitir modo de bypass de permissões"
        ativada nas configurações do Claude Code.
      - --add-dir: garante acesso de I/O à raiz do projeto.
      - --max-turns: limita custo para grupos grandes.

    Retorna (sucesso, stdout, stderr).
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"cmd_{num_cmd:03d}.log"

    cmd = _montar_invocacao(claude_path)

    try:
        if verbose:
            print(f"  ── Executando CMD {num_cmd:03d} (verbose) ──")

            process = subprocess.Popen(
                cmd, cwd=str(ROOT),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1,
            )
            try:
                process.stdin.write(texto)
                process.stdin.close()
            except Exception as e:
                return False, "", f"falha escrevendo prompt no stdin: {e}"

            output_lines = []
            for line in process.stdout:
                print(f"  | {line}", end="")
                output_lines.append(line)
            process.wait(timeout=timeout)
            stdout = "".join(output_lines)
            returncode = process.returncode
            stderr = ""
        else:
            result = subprocess.run(
                cmd, cwd=str(ROOT),
                input=texto,
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout,
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            returncode = result.returncode
            if stderr:
                stdout += f"\n--- STDERR ---\n{stderr}"

        log_path.write_text(stdout, encoding="utf-8")
        return returncode == 0, stdout, stderr

    except subprocess.TimeoutExpired:
        try:
            log_path.write_text(f"[TIMEOUT após {timeout}s]\n", encoding="utf-8")
        except Exception:
            pass
        return False, "", "timeout"

    except Exception as e:
        return False, "", f"exceção: {e}"


# ── Loop principal ──────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--de", type=int, default=0, help="Começar do CMD N")
    p.add_argument("--ate", type=int, default=0, help="Parar no CMD N (0=fim)")
    p.add_argument("--max", type=int, default=0, help="Máximo de CMDs nesta execução")
    p.add_argument("--dry", action="store_true", help="Preview sem executar")
    p.add_argument("--pausa", type=int, default=5, help="Segundos entre CMDs")
    p.add_argument("--timeout", type=int, default=900, help="Timeout por CMD (s)")
    p.add_argument("--verbose", action="store_true", help="Saída em tempo real")
    p.add_argument("--continuar-em-erro", action="store_true",
                   help="Não interrompe o batch quando um CMD falha")
    p.add_argument("--consolidar", action="store_true",
                   help="Gera planilha xlsx ao final")
    p.add_argument("--max-tentativas", type=int, default=3,
                   help="Retries por CMD (rate limit não conta)")
    args = p.parse_args()

    GRUPOS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n  ── Análise de litispendência ──")

    claude_path = verificar_claude_code()

    fila = carregar_fila()
    textos = extrair_textos_cmds(CMDS_PATH)
    if not textos:
        print(f"\n  ✗ Não consegui ler {CMDS_PATH}\n")
        sys.exit(1)

    ck = carregar_checkpoint()
    feitos_geral = set(ck.get("comandos_concluidos", []))

    todos_cmds = sorted(fila["comandos"], key=lambda c: c["num"])
    fila_de_cmds = []
    for c in todos_cmds:
        n = c["num"]
        if n in feitos_geral:
            continue
        if args.de and n < args.de:
            continue
        if args.ate and n > args.ate:
            continue
        fila_de_cmds.append(c)

    if args.max:
        fila_de_cmds = fila_de_cmds[: args.max]

    if not fila_de_cmds:
        print(f"\n  ✓ Nada pendente.")
        if args.consolidar:
            print(f"  Gerando planilha...\n")
            from services.litispendencia.scripts.consolidar_litispendencia import consolidar
            consolidar()
        return

    total_a_rodar = len(fila_de_cmds)
    print(f"  Total na fila:        {len(todos_cmds)} CMDs")
    print(f"  Já concluídos antes:  {len(feitos_geral)}")
    print(f"  A executar agora:     {total_a_rodar}")
    print(f"  Timeout/CMD:          {args.timeout}s")
    print(f"  Pasta resultados:     {GRUPOS_DIR}")
    print(f"  Permission mode:      --dangerously-skip-permissions (use só em diretório confiável)")
    print(f"  Modo:                 {'DRY-RUN' if args.dry else 'EXECUÇÃO'}")
    print()

    if args.dry:
        for c in fila_de_cmds[:10]:
            print(f"  CMD {c['num']:03d}: {c['n_grupos']} grupo(s), {c['n_procs']} proc(s)")
            print(f"           grupos: {', '.join(c['grupos'])}")
        if total_a_rodar > 10:
            print(f"  ... e mais {total_a_rodar - 10} CMDs")
        print(f"\n  (dry-run, nada foi executado)\n")
        return

    ck.setdefault("sessoes", []).append({
        "inicio": datetime.now().isoformat(),
        "fim": None,
        "cmd_inicio": ck.get("ultimo_comando", 0),
    })
    salvar_checkpoint(ck)

    sucesso_count = 0
    erro_count = 0
    inicio_sessao = datetime.now()

    try:
        for i, c in enumerate(fila_de_cmds, 1):
            n = c["num"]
            group_ids = c["grupos"]

            print(f"\n  ── CMD {n:03d} ({i}/{total_a_rodar}) ──")
            print(f"     Grupos: {', '.join(group_ids)}")

            texto = textos.get(n)
            if not texto:
                print(f"     ✗ Texto do CMD não encontrado em {CMDS_PATH.name}")
                erro_count += 1
                if not args.continuar_em_erro:
                    break
                continue

            tentativas = 0
            sucesso_cmd = False
            faltantes: list[str] = list(group_ids)

            while tentativas < args.max_tentativas:
                tentativas += 1
                t0 = time.time()

                ok, stdout, stderr = executar_cmd(
                    n, texto, claude_path, args.timeout, args.verbose,
                )
                elapsed = time.time() - t0

                rate_lim, reset = detectar_rate_limit((stdout or "") + " " + (stderr or ""))
                if rate_lim and reset:
                    print(f"     ⚠️  Rate limit detectado, reset em "
                          f"{reset.strftime('%H:%M')} (Fortaleza)")
                    esperar_rate_limit(reset, args.verbose)
                    tentativas -= 1
                    continue

                feitos_grupos, faltantes = verificar_grupos_do_cmd(group_ids)

                if not faltantes:
                    print(f"     ✓ OK ({elapsed:.1f}s) — {len(feitos_grupos)} grupo(s) salvo(s)")
                    ck.setdefault("comandos_concluidos", []).append(n)
                    ck["comandos_concluidos"] = sorted(set(ck["comandos_concluidos"]))
                    if n > ck.get("ultimo_comando", 0):
                        ck["ultimo_comando"] = n
                    salvar_checkpoint(ck)
                    sucesso_cmd = True
                    break

                if feitos_grupos:
                    print(f"     ◐ Parcial: {len(feitos_grupos)} OK, {len(faltantes)} faltando "
                          f"({', '.join(faltantes)})")
                else:
                    print(f"     ✗ Nenhum grupo salvo (tentativa {tentativas}/{args.max_tentativas})")

                if not ok:
                    log_path = LOG_DIR / f"cmd_{n:03d}.log"
                    if log_path.exists():
                        try:
                            primeiras = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[:5]
                            for ln in primeiras:
                                print(f"       log: {ln[:150]}")
                        except Exception:
                            pass

                if stderr:
                    print(f"     stderr: {stderr[:200]}")

                if tentativas < args.max_tentativas:
                    print(f"     Aguardando {args.pausa}s antes de tentar novamente...")
                    time.sleep(args.pausa)

            if not sucesso_cmd:
                erro_count += 1
                ck.setdefault("erros_por_cmd", {})[str(n)] = {
                    "tentativas": tentativas,
                    "ultimo_erro": datetime.now().isoformat(),
                    "faltantes": faltantes,
                }
                salvar_checkpoint(ck)
                if not args.continuar_em_erro:
                    print(f"\n  ✗ Parando após {tentativas} tentativas no CMD {n:03d}.")
                    print(f"     Use --continuar-em-erro para seguir adiante.")
                    print(f"     Veja o log: {LOG_DIR / f'cmd_{n:03d}.log'}\n")
                    break
            else:
                sucesso_count += 1

            if i < total_a_rodar:
                time.sleep(args.pausa)

    finally:
        if ck.get("sessoes"):
            ck["sessoes"][-1]["fim"] = datetime.now().isoformat()
            ck["sessoes"][-1]["cmd_fim"] = ck.get("ultimo_comando", 0)
            salvar_checkpoint(ck)

    duracao = datetime.now() - inicio_sessao
    mins = duracao.seconds // 60
    print(f"\n  ── Sessão encerrada ──")
    print(f"  Duração:  {mins}min")
    print(f"  Sucesso:  {sucesso_count}")
    print(f"  Erros:    {erro_count}")
    print(f"  Restantes na fila: {len(todos_cmds) - len(ck.get('comandos_concluidos', []))}")
    print()

    if args.consolidar:
        from services.litispendencia.scripts.consolidar_litispendencia import consolidar
        consolidar()


if __name__ == "__main__":
    main()