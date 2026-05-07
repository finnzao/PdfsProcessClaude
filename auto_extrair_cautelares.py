#!/usr/bin/env python3
"""
auto_extrair_cautelares.py — Executa a fila de extração via Claude Code.

Diferenças importantes vs auto_analisar.py:
  1. Detecta rate limit do Claude Code ("You've hit your limit · resets Xpm")
     e espera automaticamente até o horário de reset, retomando do mesmo CMD.
  2. Usa processos_claude_code.json como fonte da verdade do progresso.
     Como o Claude salva incrementalmente após cada processo, mesmo que
     um CMD trave no meio, os processos já feitos NÃO são reprocessados.

Uso:
    python auto_extrair_cautelares.py                    # roda todos pendentes
    python auto_extrair_cautelares.py --max 10           # só 10 comandos
    python auto_extrair_cautelares.py --de 5 --ate 20    # comandos 5 a 20
    python auto_extrair_cautelares.py --dry              # preview
    python auto_extrair_cautelares.py --consolidar       # ao final, gera planilha
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
SERVICE_DIR = ROOT / "services" / "cautelares_get_info"
FILA_PATH = SERVICE_DIR / "fila_extracao.json"
CMDS_PATH = SERVICE_DIR / "comandos_extracao.txt"
CHECKPOINT_PATH = SERVICE_DIR / "checkpoint_extracao.json"
CONTROLE_PATH = SERVICE_DIR / "processos_claude_code.json"
LOG_DIR = SERVICE_DIR / "logs"
EXTRACAO_DIR = SERVICE_DIR / "resultados" / "extracao"

IS_WINDOWS = platform.system() == "Windows"


# ── Detecção de rate limit ──────────────────────────────────────────

# Padrões reconhecidos:
#   "You've hit your limit · resets 1pm (America/Fortaleza)"
#   "Rate limit exceeded. Resets at 11:30am (UTC)"
#   "Usage limit reached, resets 6pm"
RE_RATE_LIMIT = re.compile(
    r"(?:hit\s+your\s+limit|rate[\s_-]*limit|usage[\s_-]*limit)"
    r"[^\n]{0,80}?reset(?:s)?(?:\s+at)?\s+"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
    re.IGNORECASE,
)

# Timezone explícita: "(America/Fortaleza)"
RE_TIMEZONE = re.compile(r"\(([A-Za-z_]+/[A-Za-z_]+)\)")


def detectar_rate_limit(texto: str) -> dict | None:
    m = RE_RATE_LIMIT.search(texto)
    if not m:
        return None

    hora = int(m.group(1))
    minuto = int(m.group(2)) if m.group(2) else 0
    am_pm = (m.group(3) or "").lower()

    tz_match = RE_TIMEZONE.search(texto)
    timezone = tz_match.group(1) if tz_match else None

    if am_pm == "pm" and hora < 12:
        hora += 12
    elif am_pm == "am" and hora == 12:
        hora = 0

    return {"hora": hora, "minuto": minuto, "timezone": timezone, "raw": m.group(0)}


def calcular_tempo_espera(rate_info: dict) -> tuple[float, datetime]:
    try:
        tz = ZoneInfo(rate_info["timezone"]) if rate_info["timezone"] else None
    except Exception:
        tz = None

    agora = datetime.now(tz=tz)
    alvo = agora.replace(
        hour=rate_info["hora"], minute=rate_info["minuto"],
        second=30, microsecond=0,  # 30s de margem
    )
    if alvo <= agora:
        alvo += timedelta(days=1)

    delta = (alvo - agora).total_seconds()
    return delta, alvo


def aguardar_rate_limit(rate_info: dict, comando_atual: int) -> None:
    segundos, alvo = calcular_tempo_espera(rate_info)

    print(f"\n{'=' * 60}")
    print(f"  RATE LIMIT DETECTADO")
    print(f"{'=' * 60}")
    print(f"  Mensagem do Claude:   {rate_info['raw']}")
    print(f"  Aguardando até:       {alvo.strftime('%d/%m/%Y %H:%M:%S %Z')}")
    print(f"  Tempo total de espera: {int(segundos // 60)}min {int(segundos % 60)}s")
    print(f"  Comando interrompido: CMD {comando_atual:03d}")
    print(f"  (Processos já extraídos ANTES da pausa permanecem no JSON)")
    print(f"{'=' * 60}\n")

    if segundos > 4 * 3600:
        print(f"  ⚠️  Espera maior que 4h. Confirme se é isso mesmo.")
        print(f"     Se preferir interromper, Ctrl+C e retome depois com:")
        print(f"     python auto_extrair_cautelares.py")
        return

    inicio = time.time()
    while True:
        decorrido = time.time() - inicio
        restante = segundos - decorrido
        if restante <= 0:
            break
        m_rest = int(restante // 60)
        s_rest = int(restante % 60)
        print(f"\r  Aguardando rate limit reset... {m_rest:>3}min {s_rest:02d}s   ",
              end="", flush=True)
        time.sleep(min(60, restante))

    print(f"\n\n  Reset atingido. Retomando CMD {comando_atual:03d}...\n")


# ── Setup do Claude Code ────────────────────────────────────────────

def encontrar_claude() -> str:
    p = shutil.which("claude")
    if p:
        return p
    if IS_WINDOWS:
        p = shutil.which("claude.cmd")
        if p:
            return p
    print("\n  Claude Code não encontrado no PATH.")
    print("  Instale: npm install -g @anthropic-ai/claude-code")
    print("  Depois: claude login")
    sys.exit(1)


def verificar_claude_code() -> str:
    claude_path = encontrar_claude()
    try:
        result = subprocess.run(
            [claude_path, "--version"],
            capture_output=True, text=True, timeout=10, shell=IS_WINDOWS,
            encoding="utf-8", errors="replace",
        )
        version = result.stdout.strip() or result.stderr.strip()
        print(f"  Claude Code: {version} ({claude_path})")
    except Exception:
        print(f"  Claude Code em: {claude_path} (versão não detectada)")
    return claude_path


# ── Controle global de processos ────────────────────────────────────

def carregar_controle() -> dict:
    """Lê processos_claude_code.json — fonte da verdade do progresso."""
    if CONTROLE_PATH.exists():
        try:
            return json.loads(CONTROLE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ⚠️  {CONTROLE_PATH.name} corrompido — assumindo vazio")
    return {
        "atualizado_em": datetime.now().isoformat(),
        "total_extraidos": 0,
        "processos": {},
    }


def processos_ja_extraidos() -> set[str]:
    """Retorna set de numero_processo já extraídos (do controle global)."""
    return set(carregar_controle().get("processos", {}).keys())


# ── Checkpoint do batch ─────────────────────────────────────────────

def carregar_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        try:
            return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "criado_em": datetime.now().isoformat(),
        "comandos_concluidos": [],
        "comandos_parciais": {},  # {num: [processos_feitos]}
        "ultimo_comando": 0,
    }


def salvar_checkpoint(ck: dict) -> None:
    ck["ultima_atualizacao"] = datetime.now().isoformat()
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(
        json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def marcar_concluido(num: int, processos: list[str]) -> None:
    ck = carregar_checkpoint()
    if num not in ck.get("comandos_concluidos", []):
        ck.setdefault("comandos_concluidos", []).append(num)
        ck["comandos_concluidos"].sort()
    if num > ck.get("ultimo_comando", 0):
        ck["ultimo_comando"] = num
    # Limpa parcial — agora está completo
    ck.get("comandos_parciais", {}).pop(str(num), None)
    salvar_checkpoint(ck)
    total_extraidos = len(processos_ja_extraidos())
    print(f"  ✓ Checkpoint: CMD #{num:03d} concluído | "
          f"Total geral: {total_extraidos} processos extraídos")


def marcar_parcial(num: int, processos_feitos: list[str], processos_pendentes: list[str]) -> None:
    """Registra que o CMD foi parcial — alguns processos OK, outros pendentes."""
    ck = carregar_checkpoint()
    ck.setdefault("comandos_parciais", {})[str(num)] = {
        "feitos": sorted(processos_feitos),
        "pendentes": sorted(processos_pendentes),
        "atualizado_em": datetime.now().isoformat(),
    }
    salvar_checkpoint(ck)
    print(f"  ◐ Parcial: CMD #{num:03d} | "
          f"feitos {len(processos_feitos)}/{len(processos_feitos)+len(processos_pendentes)}")


# ── Fila ────────────────────────────────────────────────────────────

def carregar_fila() -> dict:
    if not FILA_PATH.exists():
        print(f"  Fila não encontrada: {FILA_PATH}")
        print(f"  Gere com: python run.py cautelares fila-extracao")
        sys.exit(1)
    return json.loads(FILA_PATH.read_text(encoding="utf-8"))


def carregar_blocos_comandos() -> list[str]:
    if not CMDS_PATH.exists():
        print(f"  Comandos não encontrados: {CMDS_PATH}")
        sys.exit(1)
    texto = CMDS_PATH.read_text(encoding="utf-8")
    blocos = []
    bloco_atual = []
    for linha in texto.split("\n"):
        if linha.startswith("# === CMD ") and bloco_atual:
            blocos.append("\n".join(bloco_atual).strip())
            bloco_atual = []
        bloco_atual.append(linha)
    if bloco_atual:
        blocos.append("\n".join(bloco_atual).strip())
    if blocos and not blocos[0].startswith("# === CMD"):
        blocos = blocos[1:] if len(blocos) > 1 else blocos
    return blocos


def encontrar_bloco(num: int, blocos: list[str]) -> str | None:
    for b in blocos:
        if f"# === CMD {num:03d}" in b or f"# === CMD {num} " in b:
            return b
    idx = num - 1
    return blocos[idx] if 0 <= idx < len(blocos) else None


# ── Verificação de resultados ───────────────────────────────────────

def verificar_resultado(num: int, processos: list[str]) -> tuple[str, str, list[str]]:
    """
    Verifica progresso do CMD via processos_claude_code.json (fonte da verdade)
    e o JSON do CMD em si.

    Retorna ('OK'|'PARCIAL'|'ERRO', mensagem, processos_pendentes).
    """
    extraidos = processos_ja_extraidos()
    feitos = [p for p in processos if p in extraidos]
    pendentes = [p for p in processos if p not in extraidos]

    arquivo = EXTRACAO_DIR / f"extracao_{num:03d}.json"
    arquivo_existe = arquivo.exists()

    if arquivo_existe:
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            if not isinstance(dados, list):
                return "ERRO", f"Arquivo do CMD não é array: {type(dados).__name__}", pendentes
        except json.JSONDecodeError as e:
            return "ERRO", f"JSON do CMD inválido: {e}", pendentes

    if not pendentes:
        return "OK", f"todos os {len(processos)} processos extraídos", []

    if feitos:
        return "PARCIAL", (f"{len(feitos)}/{len(processos)} feitos | "
                           f"pendentes: {', '.join(pendentes)}"), pendentes

    return "ERRO", "nenhum processo foi registrado em processos_claude_code.json", pendentes


# ── Execução de um comando ──────────────────────────────────────────

def executar_comando(
    num: int,
    texto_cmd: str,
    processos: list[str],
    claude_path: str,
    timeout: int = 600,
    verbose: bool = False,
) -> tuple[str, str, list[str]]:
    """
    Executa um comando via `claude -p`.
    Retorna (status, info, processos_pendentes).
    Status: 'OK' | 'PARCIAL' | 'ERRO' | 'RATE_LIMIT' | 'TIMEOUT'.
    Para RATE_LIMIT, info é o dict com horário de reset.
    """
    extraidos_antes = processos_ja_extraidos()
    pendentes_antes = [p for p in processos if p not in extraidos_antes]

    print(f"\n{'=' * 60}")
    print(f"  CMD {num:03d} | {len(processos)} processos no batch")
    if len(pendentes_antes) < len(processos):
        feitos = len(processos) - len(pendentes_antes)
        print(f"  ⓘ {feitos} já extraídos antes — só processará {len(pendentes_antes)}")
    print(f"  {', '.join(processos)}")
    print(f"{'=' * 60}")

    # Se não há nada a fazer, marcar como OK direto
    if not pendentes_antes:
        return "OK", "todos já extraídos antes deste run", []

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"cmd_{num:03d}.log"

    # Salva o prompt em arquivo temp e usa stdin para evitar problemas
    # de escape de shell no Windows (parênteses, quebras, etc.)
    prompt_file = LOG_DIR / f"cmd_{num:03d}.prompt.txt"
    prompt_file.write_text(texto_cmd, encoding="utf-8")

    # Em Windows, claude.cmd precisa shell=True; em Linux/Mac, não.
    # Mas em Windows, passamos o prompt via stdin (não via -p "...")
    # para evitar truncamento por escape de shell.
    cmd = [
        claude_path,
        "-p",                              # modo print (não interativo)
        "--permission-mode", "acceptEdits",  # auto-aprova Read/Write/Edit
        "--output-format", "text",
    ]

    t0 = time.time()
    try:
        # Lê o prompt como stdin
        with open(prompt_file, "r", encoding="utf-8") as f_stdin:
            if verbose:
                process = subprocess.Popen(
                    cmd, cwd=str(ROOT),
                    stdin=f_stdin,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    shell=IS_WINDOWS,
                    encoding="utf-8", errors="replace",
                )
                output_lines = []
                for line in process.stdout:
                    print(f"    {line}", end="")
                    output_lines.append(line)
                process.wait(timeout=timeout)
                output = "".join(output_lines)
            else:
                result = subprocess.run(
                    cmd, cwd=str(ROOT),
                    stdin=f_stdin,
                    capture_output=True, text=True, timeout=timeout,
                    shell=IS_WINDOWS,
                    encoding="utf-8", errors="replace",
                )
                output = result.stdout or ""
                if result.stderr:
                    output += f"\n--- STDERR ---\n{result.stderr}"

        log_file.write_text(output, encoding="utf-8")
        dt = time.time() - t0
        mins, segs = int(dt // 60), int(dt % 60)

        # Verifica rate limit ANTES de avaliar sucesso
        rate_info = detectar_rate_limit(output)
        if rate_info:
            # Mesmo se travou por rate limit, pode ter processado alguns
            status, msg, pendentes = verificar_resultado(num, processos)
            extraidos_durante = set(processos) - set(pendentes) - set(p for p in processos if p in extraidos_antes)
            if extraidos_durante:
                print(f"  ⓘ Antes do rate limit, {len(extraidos_durante)} foram extraídos")
            return "RATE_LIMIT", rate_info, pendentes

        status, msg, pendentes = verificar_resultado(num, processos)

        if status == "OK":
            print(f"  ✓ OK em {mins}m{segs:02d}s | {msg}")
        elif status == "PARCIAL":
            print(f"  ◐ PARCIAL em {mins}m{segs:02d}s | {msg}")
            print(f"     Log: {log_file}")
        else:
            print(f"  ✗ ERRO em {mins}m{segs:02d}s: {msg}")
            print(f"     Log: {log_file}")
            # Diagnóstico: se falhou rápido (<30s) sem extrair nada, mostra preview
            if dt < 30 and not verbose:
                preview = output[:600] if output else "(saída vazia)"
                print(f"     ── Preview do log ──")
                for linha in preview.splitlines()[:15]:
                    print(f"       {linha}")
                if len(output) > 600:
                    print(f"       ... ({len(output) - 600} chars omitidos, ver arquivo)")
                print(f"     ── fim do preview ──")

        return status, msg, pendentes

    except subprocess.TimeoutExpired:
        dt = time.time() - t0
        print(f"  ✗ TIMEOUT após {int(dt // 60)}m{int(dt % 60):02d}s")
        if verbose and 'process' in locals():
            process.kill()
        # Mesmo com timeout, alguns podem ter sido processados
        status, msg, pendentes = verificar_resultado(num, processos)
        if status == "PARCIAL":
            print(f"  ⓘ Apesar do timeout, {len(processos) - len(pendentes)} foram extraídos")
            return "PARCIAL", f"timeout (parcial: {msg})", pendentes
        return "TIMEOUT", "timeout", pendentes

    except Exception as e:
        dt = time.time() - t0
        print(f"  ✗ ERRO em {int(dt // 60)}m{int(dt % 60):02d}s: {e}")
        status, msg, pendentes = verificar_resultado(num, processos)
        if status == "PARCIAL":
            return "PARCIAL", f"erro (parcial: {msg})", pendentes
        return "ERRO", str(e), pendentes


# ── Consolidação ────────────────────────────────────────────────────

def consolidar_resultados() -> None:
    print(f"\n{'=' * 60}")
    print(f"  CONSOLIDANDO PLANILHA DE CUSTODIADOS")
    print(f"{'=' * 60}\n")
    try:
        sys.path.insert(0, str(ROOT))
        from services.cautelares_get_info.scripts.consolidar_extracao import consolidar
        consolidar()
    except ImportError as e:
        print(f"  ✗ Erro ao importar consolidar_extracao: {e}")
    except Exception as e:
        print(f"  ✗ Erro na consolidação: {e}")


# ── Main ────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Executa extração de custodiados via Claude Code (com retry de rate limit e salvamento incremental)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--de", type=int, default=0, help="Começar do comando N")
    p.add_argument("--ate", type=int, default=0, help="Parar no comando N")
    p.add_argument("--max", type=int, default=0, help="Máximo de comandos")
    p.add_argument("--dry", action="store_true", help="Preview sem executar")
    p.add_argument("--pausa", type=int, default=5, help="Segundos entre comandos")
    p.add_argument("--timeout", type=int, default=600, help="Timeout por comando (s)")
    p.add_argument("--verbose", action="store_true", help="Saída em tempo real")
    p.add_argument("--continuar-em-erro", action="store_true",
                   help="Não parar em caso de erro")
    p.add_argument("--consolidar", action="store_true",
                   help="Gera planilha xlsx ao final")
    p.add_argument("--max-tentativas", type=int, default=3,
                   help="Tentativas por comando após erro/parcial")
    args = p.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  AUTO-EXTRAIR CUSTODIADOS — Claude Code")
    print(f"{'=' * 60}\n")

    claude_path = verificar_claude_code()

    fila = carregar_fila()
    blocos = carregar_blocos_comandos()
    comandos_fila = fila.get("comandos", [])
    total = len(comandos_fila)

    extraidos_inicio = processos_ja_extraidos()
    print(f"  Fila: {total} comandos")
    print(f"  Já extraídos no controle global: {len(extraidos_inicio)} processos")

    pendentes = []
    cmds_skip_total = 0
    for cmd in comandos_fila:
        n = cmd["num"]
        if args.de and n < args.de:
            continue
        if args.ate and n > args.ate:
            continue
        # Pula CMD se TODOS os processos dele já estão extraídos
        if all(p in extraidos_inicio for p in cmd["processos"]):
            cmds_skip_total += 1
            continue
        pendentes.append(cmd)

    if args.max:
        pendentes = pendentes[:args.max]

    if cmds_skip_total:
        print(f"  CMDs com tudo extraído (pulados): {cmds_skip_total}")

    if not pendentes:
        print("\n  Nenhum comando pendente.\n")
        if args.consolidar:
            consolidar_resultados()
        return

    print(f"  Pendentes: {len(pendentes)}")
    print(f"  Timeout: {args.timeout}s | Pausa: {args.pausa}s")
    if args.consolidar:
        print(f"  Consolidar ao final: SIM")
    print()

    if args.dry:
        print("  [DRY RUN]\n")
        for cmd in pendentes:
            falt = [p for p in cmd["processos"] if p not in extraidos_inicio]
            print(f"  CMD {cmd['num']:03d} | {len(falt)}/{len(cmd['processos'])} a processar")
            for p in cmd["processos"]:
                marca = "✓" if p in extraidos_inicio else " "
                print(f"    [{marca}] {p}")
            print()
        return

    ok = parciais = erros = rate_limits = 0
    t_total = time.time()

    i = 0
    while i < len(pendentes):
        cmd = pendentes[i]
        n = cmd["num"]
        procs = cmd["processos"]

        bloco = encontrar_bloco(n, blocos)
        if not bloco:
            print(f"  ✗ CMD {n:03d}: bloco não encontrado")
            erros += 1
            i += 1
            continue

        # Loop de tentativas (rate limit não conta como tentativa falha)
        tentativas = 0
        sucesso_final = False
        while tentativas < args.max_tentativas:
            tentativas += 1
            status, info, procs_pendentes = executar_comando(
                n, bloco, procs, claude_path,
                timeout=args.timeout, verbose=args.verbose,
            )

            if status == "OK":
                marcar_concluido(n, procs)
                ok += 1
                sucesso_final = True
                break

            elif status == "RATE_LIMIT":
                rate_limits += 1
                # Marca o que já foi feito antes do rate limit
                feitos = [p for p in procs if p not in procs_pendentes]
                if feitos:
                    marcar_parcial(n, feitos, procs_pendentes)
                aguardar_rate_limit(info, n)
                tentativas -= 1  # Rate limit não conta como tentativa
                continue

            elif status == "PARCIAL":
                feitos = [p for p in procs if p not in procs_pendentes]
                marcar_parcial(n, feitos, procs_pendentes)
                if tentativas < args.max_tentativas:
                    print(f"  Tentativa {tentativas}/{args.max_tentativas}: "
                          f"{len(procs_pendentes)} pendente(s). Retentando em 10s...")
                    time.sleep(10)
                    continue
                else:
                    parciais += 1
                    break

            elif status in ("ERRO", "TIMEOUT"):
                if tentativas < args.max_tentativas:
                    print(f"  Tentativa {tentativas}/{args.max_tentativas} falhou. "
                          f"Retentando em 10s...")
                    time.sleep(10)
                    continue
                else:
                    erros += 1
                    break

        if not sucesso_final and not args.continuar_em_erro:
            print(f"\n  Parando após problema no CMD {n:03d}")
            print(f"  Use --continuar-em-erro para prosseguir")
            print(f"  Para retomar depois: python auto_extrair_cautelares.py")
            print(f"  Os processos já extraídos foram preservados em "
                  f"resultados/extracao/extracao_{n:03d}.json")
            break

        # Pausa entre comandos
        if i + 1 < len(pendentes):
            time.sleep(args.pausa)

        i += 1

    dt = time.time() - t_total
    mins, segs = int(dt // 60), int(dt % 60)
    extraidos_fim = processos_ja_extraidos()
    novos = len(extraidos_fim) - len(extraidos_inicio)

    print(f"\n{'=' * 60}")
    print(f"  RESULTADO")
    print(f"{'=' * 60}")
    print(f"  ✓ {ok} CMDs OK | ◐ {parciais} parciais | ✗ {erros} erros")
    if rate_limits:
        print(f"  ⏸  {rate_limits} rate limits superados")
    print(f"  Processos extraídos neste run: {novos}")
    print(f"  Total no controle global:      {len(extraidos_fim)}")
    print(f"  Tempo: {mins}m{segs:02d}s")
    print(f"{'=' * 60}\n")

    if args.consolidar and (ok > 0 or parciais > 0):
        consolidar_resultados()


if __name__ == "__main__":
    main()
