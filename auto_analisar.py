#!/usr/bin/env python3
"""
auto_analisar.py — Executa os comandos da fila via Claude Code (claude -p).

Requisitos:
    - Claude Code instalado (npm install -g @anthropic-ai/claude-code)
    - Autenticado (claude login)

Uso:
    python auto_analisar.py                          # executa todos os pendentes
    python auto_analisar.py --de 5                   # comeca do comando 5
    python auto_analisar.py --de 5 --ate 10          # executa do 5 ao 10
    python auto_analisar.py --max 20                 # executa no maximo 20 comandos
    python auto_analisar.py --dry                    # mostra o que faria sem executar
    python auto_analisar.py --pausa 10               # 10 segundos entre comandos (default: 5)
    python auto_analisar.py --timeout 600            # timeout por comando em segundos (default: 300)
    python auto_analisar.py --verbose                # mostra saida do Claude Code em tempo real
    python auto_analisar.py --consolidar             # gera planilha de triagem ao final
    python auto_analisar.py --max 10 --consolidar    # analisa 10 e gera planilha
"""

import json, sys, time, argparse, subprocess, shutil, platform
from pathlib import Path

ROOT = Path(__file__).parent
SERVICE_DIR = ROOT / "services" / "analisar_processo"
FILA_PATH = SERVICE_DIR / "fila.json"
CMDS_PATH = SERVICE_DIR / "comandos_claude_code.txt"
CHECKPOINT_PATH = SERVICE_DIR / "checkpoint.json"
LOG_DIR = SERVICE_DIR / "logs"
RESULT_DIR = ROOT / "result" / "analisar_processo"

IS_WINDOWS = platform.system() == "Windows"


def _find_claude():
    """Encontra o executavel do Claude Code, incluindo .cmd no Windows."""
    # Tentar direto
    p = shutil.which("claude")
    if p:
        return p
    # Windows: npm instala como claude.cmd
    if IS_WINDOWS:
        p = shutil.which("claude.cmd")
        if p:
            return p
    return None


def verificar_claude_code():
    """Verifica se o Claude Code esta instalado e acessivel."""
    claude_path = _find_claude()
    if not claude_path:
        print("\n  Claude Code nao encontrado no PATH.")
        print("  Instale: npm install -g @anthropic-ai/claude-code")
        print("  Depois: claude login")
        sys.exit(1)

    try:
        result = subprocess.run(
            [claude_path, "--version"],
            capture_output=True, text=True, timeout=10,
            shell=IS_WINDOWS,
        )
        version = result.stdout.strip() or result.stderr.strip()
        print(f"  Claude Code: {version} ({claude_path})")
    except Exception as e:
        print(f"  Claude Code em: {claude_path} (versao nao detectada)")

    return claude_path


def carregar_checkpoint():
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    return {"processos_analisados": {}, "comandos_concluidos": [], "ultimo_comando": 0}


def salvar_checkpoint(ck):
    from datetime import datetime
    ck["ultima_atualizacao"] = datetime.now().isoformat()
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")


def carregar_fila():
    if not FILA_PATH.exists():
        print("  Fila nao encontrada. Execute: python run.py analise fila")
        sys.exit(1)
    return json.loads(FILA_PATH.read_text(encoding="utf-8"))


def carregar_comandos_texto():
    """Parseia o arquivo de comandos em blocos separados."""
    if not CMDS_PATH.exists():
        print("  Comandos nao encontrados. Execute: python run.py analise fila")
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


def executar_comando_claude(num, texto_cmd, processos, claude_path, timeout=300, verbose=False):
    """Executa um comando via `claude -p` com o prompt completo."""
    print(f"\n{'='*60}")
    print(f"  CMD {num:03d} | {len(processos)} processos")
    print(f"  {', '.join(processos[:3])}{'...' if len(processos) > 3 else ''}")
    print(f"{'='*60}")

    t0 = time.time()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"cmd_{num:03d}.log"

    cmd = [
        claude_path,
        "-p", texto_cmd,
        "--allowedTools", "Read,Write,Edit,Bash",
        "--max-turns", "30",
        "--output-format", "text",
    ]

    try:
        if verbose:
            process = subprocess.Popen(
                cmd, cwd=str(ROOT),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                shell=IS_WINDOWS,
            )
            output_lines = []
            for line in process.stdout:
                print(f"    {line}", end="")
                output_lines.append(line)
            process.wait(timeout=timeout)
            output = "".join(output_lines)
            returncode = process.returncode
        else:
            result = subprocess.run(
                cmd, cwd=str(ROOT),
                capture_output=True, text=True, timeout=timeout,
                shell=IS_WINDOWS,
            )
            output = result.stdout
            returncode = result.returncode
            if result.stderr:
                output += f"\n--- STDERR ---\n{result.stderr}"

        log_file.write_text(output, encoding="utf-8")

        dt = time.time() - t0
        mins = int(dt // 60)
        segs = int(dt % 60)

        if returncode != 0:
            print(f"  Retorno {returncode} em {mins}m{segs:02d}s | Log: {log_file}")

        resultados_ok = verificar_resultados(num, processos)

        if resultados_ok:
            print(f"  OK em {mins}m{segs:02d}s")
        else:
            print(f"  Concluido em {mins}m{segs:02d}s mas resultados incompletos | Log: {log_file}")

        return resultados_ok or returncode == 0

    except subprocess.TimeoutExpired:
        dt = time.time() - t0
        mins = int(dt // 60)
        segs = int(dt % 60)
        print(f"  TIMEOUT ({mins}m{segs:02d}s)")
        if verbose and 'process' in locals():
            process.kill()
        return False

    except Exception as e:
        dt = time.time() - t0
        mins = int(dt // 60)
        segs = int(dt % 60)
        print(f"  ERRO em {mins}m{segs:02d}s: {e}")
        return False


def verificar_resultados(num, processos):
    """Verifica se os arquivos de resultado foram gerados."""
    resultados_dir = SERVICE_DIR / "resultados"
    analises_dir = resultados_dir / "analises"

    triagem = resultados_dir / f"triagem_{num:03d}.json"
    tem_triagem = triagem.exists()

    analises_encontradas = 0
    for proc in processos:
        nome_arq = proc.replace(".", "_").replace("-", "_") + ".md"
        if (analises_dir / nome_arq).exists():
            analises_encontradas += 1

    status = "OK" if tem_triagem else "FALTA"
    print(f"  Triagem: {status} | Analises: {analises_encontradas}/{len(processos)}")

    return tem_triagem or analises_encontradas > 0


def marcar_concluido(num, processos):
    """Registra comando como feito no checkpoint."""
    from datetime import datetime

    ck = carregar_checkpoint()

    if num not in ck.get("comandos_concluidos", []):
        ck.setdefault("comandos_concluidos", []).append(num)
        ck["comandos_concluidos"].sort()

    if num > ck.get("ultimo_comando", 0):
        ck["ultimo_comando"] = num

    agora = datetime.now().isoformat()
    for p in processos:
        ck.setdefault("processos_analisados", {})[p] = {
            "comando": num,
            "data": agora,
            "arquivo": f"resultados/triagem_{num:03d}.json",
        }

    salvar_checkpoint(ck)
    print(f"  Checkpoint: CMD #{num:03d} | {len(processos)} processos | Total: {len(ck['processos_analisados'])}")


def consolidar_triagem():
    """Gera a planilha de triagem priorizada."""
    print(f"\n{'='*60}")
    print(f"  CONSOLIDANDO PLANILHA DE TRIAGEM")
    print(f"{'='*60}")

    try:
        sys.path.insert(0, str(ROOT))
        from common.consolidar_analise import ConsolidarAnalise
        ConsolidarAnalise(SERVICE_DIR, RESULT_DIR).consolidar()
        print(f"\n  Planilha em: {RESULT_DIR / 'triagem_processos.xlsx'}")
    except ImportError as e:
        print(f"  Erro ao importar consolidar_analise: {e}")
        print("  Execute manualmente: python run.py analise consolidar")
    except Exception as e:
        print(f"  Erro na consolidacao: {e}")
        print("  Execute manualmente: python run.py analise consolidar")


def main():
    parser = argparse.ArgumentParser(
        description="Executa analise juridica via Claude Code (claude -p)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python auto_analisar.py                          # todos os pendentes
  python auto_analisar.py --dry                    # ver o que faria
  python auto_analisar.py --de 5 --ate 10          # comandos 5 a 10
  python auto_analisar.py --max 3 --verbose        # 3 comandos com saida detalhada
  python auto_analisar.py --consolidar             # gera planilha ao final
  python auto_analisar.py --max 10 --consolidar    # analisa 10 e gera planilha
        """,
    )
    parser.add_argument("--de", type=int, default=0, help="Comecar do comando N")
    parser.add_argument("--ate", type=int, default=0, help="Parar no comando N")
    parser.add_argument("--max", type=int, default=0, help="Maximo de comandos")
    parser.add_argument("--dry", action="store_true", help="Mostrar sem executar")
    parser.add_argument("--pausa", type=int, default=5, help="Segundos entre comandos")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout por comando (seg)")
    parser.add_argument("--verbose", action="store_true", help="Saida em tempo real")
    parser.add_argument("--continuar-em-erro", action="store_true", help="Nao parar em erro")
    parser.add_argument("--consolidar", action="store_true", help="Gerar planilha de triagem ao final")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  AUTO-ANALISAR — Claude Code (claude -p)")
    print(f"{'='*60}\n")

    # Verificar Claude Code
    claude_path = verificar_claude_code()

    fila = carregar_fila()
    ck = carregar_checkpoint()
    blocos = carregar_comandos_texto()
    comandos_fila = fila.get("comandos", [])
    concluidos = set(ck.get("comandos_concluidos", []))
    total = len(comandos_fila)

    filtro = fila.get("filtro_classe", "TODAS")
    print(f"  Fila: {total} comandos | Concluidos: {len(concluidos)} | Filtro: {filtro}")

    pendentes = []
    for cmd in comandos_fila:
        n = cmd["num"]
        if n in concluidos: continue
        if args.de and n < args.de: continue
        if args.ate and n > args.ate: continue
        pendentes.append(cmd)

    if args.max:
        pendentes = pendentes[: args.max]

    if not pendentes:
        print("  Nenhum comando pendente.\n")
        if args.consolidar:
            consolidar_triagem()
        return

    print(f"  Pendentes: {len(pendentes)}")
    print(f"  Timeout: {args.timeout}s | Pausa: {args.pausa}s")
    if args.consolidar:
        print(f"  Consolidar ao final: SIM")

    if args.dry:
        print("\n  [DRY RUN]\n")
        for cmd in pendentes:
            n = cmd["num"]
            procs = cmd["processos"]
            tipo = cmd.get("tipo", "?")
            print(f"  CMD {n:03d} | {tipo} | {len(procs)} processos")
            for p in procs[:3]:
                print(f"    - {p}")
            if len(procs) > 3:
                print(f"    ... +{len(procs)-3}")
            print()
        return

    ok = erros = 0
    t_total = time.time()

    for i, cmd in enumerate(pendentes):
        n = cmd["num"]
        procs = cmd["processos"]

        bloco_texto = None
        for bloco in blocos:
            if f"# === CMD {n:03d}" in bloco or f"# === CMD {n} " in bloco:
                bloco_texto = bloco
                break

        if not bloco_texto:
            idx = n - 1
            if idx < len(blocos):
                bloco_texto = blocos[idx]
            else:
                print(f"  CMD {n:03d}: bloco nao encontrado")
                erros += 1
                continue

        sucesso = executar_comando_claude(
            n, bloco_texto, procs, claude_path,
            timeout=args.timeout, verbose=args.verbose,
        )

        if sucesso:
            marcar_concluido(n, procs)
            ok += 1
        else:
            erros += 1
            if not args.continuar_em_erro:
                print(f"  Parando apos erro no CMD {n:03d}")
                print(f"  Use --continuar-em-erro para prosseguir")
                break

        restantes = len(pendentes) - (i + 1)
        if restantes > 0:
            print(f"  Restam: {restantes} | Pausa {args.pausa}s...")
            time.sleep(args.pausa)

    dt = time.time() - t_total
    mins = int(dt // 60)
    segs = int(dt % 60)
    total_done = len(concluidos) + ok

    print(f"\n{'='*60}")
    print(f"  RESULTADO")
    print(f"  {ok} ok, {erros} erros | {mins}m{segs:02d}s")
    print(f"  Progresso: {total_done}/{total} ({total_done/total*100:.0f}%)")
    if total_done < total:
        print(f"  Restam: {total - total_done}")
        print(f"  Retomar: python auto_analisar.py")
    else:
        print(f"  COMPLETO!")
    print(f"{'='*60}")

    # Consolidar planilha ao final se solicitado
    if args.consolidar and ok > 0:
        consolidar_triagem()
    elif args.consolidar and ok == 0:
        print("\n  Nenhuma analise concluida, pulando consolidacao.")


if __name__ == "__main__":
    main()