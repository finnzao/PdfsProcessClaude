"""
services/litispendencia/main.py — CLI do service de análise de litispendência.

Roda via run.py:
    python run.py litispendencia fila
    python run.py litispendencia status
    python run.py litispendencia analisar
    python run.py litispendencia pausa
    python run.py litispendencia marcar <CMD_NUM> <GROUP_IDs...>
    python run.py litispendencia consolidar
    python run.py litispendencia reset
    python run.py litispendencia limpar-controle
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.checkpoint import CheckpointManager
from common.sessao import SessaoManager
from common.utils import DIR_RESULT, DIR_FILES

SERVICE_DIR = Path(__file__).parent
RESULT_DIR = DIR_RESULT / "litispendencia"
CONTROLE_PATH = SERVICE_DIR / "controle_grupos.json"
FILA_PATH = SERVICE_DIR / "fila.json"
CMDS_PATH = SERVICE_DIR / "comandos_claude_code.txt"
CHECKPOINT_PATH = SERVICE_DIR / "checkpoint.json"


def carregar_controle() -> dict:
    if CONTROLE_PATH.exists():
        try:
            return json.loads(CONTROLE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"atualizado_em": "", "total_analisados": 0, "grupos": {}}


def cmd_fila(args):
    """Gera fila a partir do xlsx."""
    from services.litispendencia.scripts.fila_litispendencia import gerar_fila, ABAS_DEFAULT

    xlsx = None
    abas = ABAS_DEFAULT
    forcar = "--forcar" in args
    for a in args:
        if a.startswith("--xlsx="):
            xlsx = Path(a.split("=", 1)[1])
        elif a.startswith("--abas="):
            abas = [s.strip() for s in a.split("=", 1)[1].split(",") if s.strip()]

    xlsx = xlsx or (DIR_FILES / "litispendencia.xlsx")
    gerar_fila(xlsx, abas, forcar)


def cmd_status(args):
    """Mostra progresso granular: grupos analisados vs total."""
    if not FILA_PATH.exists():
        print("\n  Fila não gerada. Rode: python run.py litispendencia fila\n")
        return

    fila = json.loads(FILA_PATH.read_text(encoding="utf-8"))
    ck = CheckpointManager(CHECKPOINT_PATH).carregar()
    controle = carregar_controle()
    grupos_feitos = set(controle.get("grupos", {}).keys())

    total_cmd = fila.get("total_comandos", 0)
    total_grupos = fila.get("total_grupos", 0)
    total_procs = fila.get("total_processos", 0)
    done_cmd = len(ck.get("comandos_concluidos", []))

    # Grupos feitos que pertencem à fila atual
    grupos_da_fila = set()
    for c in fila.get("comandos", []):
        grupos_da_fila.update(c.get("grupos", []))
    done_grupos = len(grupos_da_fila & grupos_feitos)

    pct = done_grupos / total_grupos * 100 if total_grupos else 0
    bar = "#" * int(pct // 2.5) + "-" * (40 - int(pct // 2.5))

    print(f"\n  ── Status da análise de litispendência ──")
    print(f"  [{bar}] {pct:.1f}%")
    print(f"  Comandos:  {done_cmd}/{total_cmd} concluídos")
    print(f"  Grupos:    {done_grupos}/{total_grupos} analisados")
    print(f"  Processos: {total_procs} no total")
    print(f"  No controle geral: {len(grupos_feitos)} grupos (todas as filas)")

    if done_cmd < total_cmd:
        proximo = ck.get("ultimo_comando", 0) + 1
        print(f"\n  Próximo CMD: ~{proximo:03d}")
        print(f"  Retomar com: python auto_analisar_litispendencia.py")
    else:
        print(f"\n  ✓ Análise completa! Rode 'consolidar' para gerar a planilha.")
    print()


def cmd_analisar(args):
    """Abre sessão de trabalho (compat com padrão do projeto)."""
    SessaoManager(CHECKPOINT_PATH).inicio()
    print(f"  Cole os comandos de: {CMDS_PATH}")
    print(f"  Ou rode: python auto_analisar_litispendencia.py")


def cmd_pausa(args):
    """Fecha sessão de trabalho."""
    SessaoManager(CHECKPOINT_PATH).fim(FILA_PATH)


def cmd_marcar(args):
    """Marca CMD concluído manualmente.

    Uso: marcar <CMD_NUM> <group_id_1> <group_id_2> ...
    """
    if len(args) < 1:
        print("  USO: marcar <CMD_NUM> [<group_id_1> <group_id_2> ...]")
        return

    cmd_num = int(args[0])
    group_ids = args[1:]

    CheckpointManager(CHECKPOINT_PATH).marcar_concluido(
        cmd_num,
        group_ids,
        f"resultados/grupos/ (grupos: {', '.join(group_ids)})",
    )


def cmd_consolidar(args):
    """Gera planilha xlsx final."""
    from services.litispendencia.scripts.consolidar_litispendencia import consolidar
    consolidar()


def cmd_reset(args):
    """Limpa fila + checkpoint (preserva controle_grupos e resultados)."""
    arquivos = [FILA_PATH, CMDS_PATH, CHECKPOINT_PATH]
    for f in arquivos:
        if f.exists():
            f.unlink()
            print(f"  Removido: {f.name}")
    print(f"\n  ✓ Reset OK (fila + checkpoint).")
    print(f"     Preservados:")
    print(f"     - resultados/grupos/*.json (análises do Claude)")
    print(f"     - controle_grupos.json (controle de retomada)")
    print(f"\n     Para zerar TUDO: rode 'limpar-controle --confirmar' e apague resultados/grupos/\n")


def cmd_limpar_controle(args):
    """Zera controle_grupos.json (usar com cuidado!)."""
    if "--confirmar" not in args:
        print("\n  ⚠️  Esta ação zera o controle de retomada.")
        print(f"     Próxima geração de fila vai considerar TODOS os")
        print(f"     grupos como pendentes (mesmo os já analisados).")
        print(f"\n     Para confirmar: python run.py litispendencia limpar-controle --confirmar\n")
        return

    if CONTROLE_PATH.exists():
        backup = SERVICE_DIR / f"controle_grupos.bkp_{datetime.now():%Y%m%d_%H%M%S}.json"
        CONTROLE_PATH.rename(backup)
        print(f"  ✓ Backup salvo em: {backup.name}")
    print(f"  ✓ Controle zerado.")


COMANDOS = {
    "fila": cmd_fila,
    "status": cmd_status,
    "analisar": cmd_analisar,
    "pausa": cmd_pausa,
    "marcar": cmd_marcar,
    "consolidar": cmd_consolidar,
    "reset": cmd_reset,
    "limpar-controle": cmd_limpar_controle,
}


def executar(comando: str, args: list | None = None):
    args = args or []
    handler = COMANDOS.get(comando)

    if handler:
        handler(args)
        return

    print(f"\n  Comando desconhecido: {comando}\n")
    print(f"  ── Comandos disponíveis ──")
    print(f"    fila                  Gera fila de comandos do xlsx")
    print(f"                          flags: --xlsx=<path> --abas=A,B --forcar")
    print(f"    status                Mostra progresso (CMDs e grupos)")
    print(f"    analisar              Abre sessão de trabalho")
    print(f"    pausa                 Fecha sessão de trabalho")
    print(f"    marcar <N> <ids...>   Marca CMD concluído manualmente")
    print(f"    consolidar            Gera planilha xlsx final")
    print(f"    reset                 Limpa fila + checkpoint")
    print(f"    limpar-controle       Zera controle_grupos.json (com backup)")
    print()
    print(f"  ── Workflow ──")
    print(f"    1. python run.py litispendencia fila")
    print(f"    2. python auto_analisar_litispendencia.py --consolidar")
    print()
