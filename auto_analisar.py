#!/usr/bin/env python3
"""
auto_analisar.py — Executa os comandos da fila via Claude Agent SDK (Python).

Requisitos:
    pip install claude-agent-sdk

Uso:
    python auto_analisar.py                  # executa todos os pendentes
    python auto_analisar.py --de 5           # comeca do comando 5
    python auto_analisar.py --de 5 --ate 10  # executa do 5 ao 10
    python auto_analisar.py --max 20         # executa no maximo 20 comandos
    python auto_analisar.py --dry            # mostra o que faria sem executar
"""

import json, sys, time, argparse, asyncio
from pathlib import Path

ROOT = Path(__file__).parent
SERVICE_DIR = ROOT / "services" / "analisar_processo"
FILA_PATH = SERVICE_DIR / "fila.json"
CMDS_PATH = SERVICE_DIR / "comandos_claude_code.txt"
CHECKPOINT_PATH = SERVICE_DIR / "checkpoint.json"


def carregar_checkpoint():
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    return {"processos_analisados": {}, "comandos_concluidos": [], "ultimo_comando": 0}


def carregar_fila():
    if not FILA_PATH.exists():
        print("  Fila nao encontrada. Execute: python run.py analise fila")
        sys.exit(1)
    return json.loads(FILA_PATH.read_text(encoding="utf-8"))


def carregar_comandos_texto():
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
    return blocos


async def executar_comando_sdk(num, texto_cmd, processos):
    from claude_agent_sdk import query, ClaudeAgentOptions

    print(f"\n{'='*60}")
    print(f"  CMD {num:03d} | {len(processos)} processos")
    print(f"  {', '.join(processos[:3])}{'...' if len(processos) > 3 else ''}")
    print(f"{'='*60}")

    t0 = time.time()

    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Edit", "Bash"],
        max_turns=30,
        cwd=str(ROOT),
    )

    resposta = []
    try:
        async for msg in query(prompt=texto_cmd, options=options):
            if hasattr(msg, "content"):
                for bloco in msg.content:
                    if hasattr(bloco, "text"):
                        resposta.append(bloco.text)
                    elif hasattr(bloco, "type") and bloco.type == "text":
                        resposta.append(bloco.text)

        dt = time.time() - t0
        mins = int(dt // 60)
        segs = int(dt % 60)

        resultado_path = SERVICE_DIR / "resultados" / f"analise_{num:03d}.csv"
        if resultado_path.exists():
            linhas = resultado_path.read_text(encoding="utf-8").strip().split("\n")
            print(f"  OK em {mins}m{segs:02d}s | CSV: {len(linhas)-1} registros")
        else:
            print(f"  OK em {mins}m{segs:02d}s | AVISO: CSV nao gerado")

        return True

    except Exception as e:
        dt = time.time() - t0
        mins = int(dt // 60)
        segs = int(dt % 60)
        print(f"  ERRO em {mins}m{segs:02d}s: {e}")
        return False


def marcar_concluido(num, processos):
    from common.checkpoint import CheckpointManager
    cm = CheckpointManager(CHECKPOINT_PATH)
    cm.marcar_concluido(num, processos, f"resultados/analise_{num:03d}.csv")


async def main_async(args):
    fila = carregar_fila()
    ck = carregar_checkpoint()
    blocos = carregar_comandos_texto()
    comandos_fila = fila.get("comandos", [])
    concluidos = set(ck.get("comandos_concluidos", []))
    total = len(comandos_fila)

    print(f"\n  Fila: {total} comandos | Concluidos: {len(concluidos)}")

    pendentes = []
    for cmd in comandos_fila:
        n = cmd["num"]
        if n in concluidos:
            continue
        if args.de and n < args.de:
            continue
        if args.ate and n > args.ate:
            continue
        pendentes.append(cmd)

    if args.max:
        pendentes = pendentes[:args.max]

    if not pendentes:
        print("  Nenhum comando pendente.\n")
        return

    print(f"  Pendentes: {len(pendentes)}")

    if args.dry:
        print("  [DRY RUN]\n")
        for cmd in pendentes:
            n = cmd["num"]
            if n - 1 < len(blocos):
                texto = blocos[n - 1]
                print(f"  CMD {n:03d} | {len(cmd['processos'])} procs")
                for linha in texto.split("\n")[:4]:
                    print(f"    {linha}")
                print()
        return

    ok = erros = 0
    t_total = time.time()

    for i, cmd in enumerate(pendentes):
        n = cmd["num"]
        procs = cmd["processos"]

        if n - 1 < len(blocos):
            texto = blocos[n - 1]
        else:
            print(f"  CMD {n:03d}: bloco nao encontrado")
            erros += 1
            continue

        sucesso = await executar_comando_sdk(n, texto, procs)

        if sucesso:
            marcar_concluido(n, procs)
            ok += 1
        else:
            erros += 1
            print(f"  Parando apos erro no CMD {n:03d}")
            break

        restantes = len(pendentes) - (i + 1)
        if restantes > 0:
            print(f"  Restam: {restantes} | Pausa {args.pausa}s...")
            await asyncio.sleep(args.pausa)

    dt = time.time() - t_total
    mins = int(dt // 60)
    segs = int(dt % 60)
    total_done = len(concluidos) + ok

    print(f"\n{'='*60}")
    print(f"  {ok} ok, {erros} erros | {mins}m{segs:02d}s")
    print(f"  Progresso: {total_done}/{total} ({total_done/total*100:.0f}%)")
    if total_done < total:
        print(f"  Restam: {total - total_done}")
    else:
        print(f"  COMPLETO. Execute: python run.py analise consolidar")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Executa analise via Claude Agent SDK")
    parser.add_argument("--de", type=int, default=0)
    parser.add_argument("--ate", type=int, default=0)
    parser.add_argument("--max", type=int, default=0)
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--pausa", type=int, default=5)
    args = parser.parse_args()

    try:
        import claude_agent_sdk
    except ImportError:
        print("\n  Claude Agent SDK nao encontrado.")
        print("  Instale: pip install claude-agent-sdk")
        print()
        sys.exit(1)

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
