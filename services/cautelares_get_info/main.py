"""
services/cautelares_get_info/main.py — CLI do service.

Pipeline NOVO (Claude Code lê markdowns):
  python run.py cautelares fila-extracao        # gera fila
  python run.py cautelares status-extracao      # progresso (granular por processo)
  python run.py cautelares marcar-extracao      # marca CMD manualmente
  python run.py cautelares consolidar-extracao  # gera planilha xlsx
  python run.py cautelares reset-extracao       # zera fila + checkpoint
  python run.py cautelares limpar-controle      # zera processos_claude_code.json

Pipeline ANTIGO (mantido por compat):
  fila, status, analisar, pausa, marcar, consolidar, reset
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.fila_base import FilaBase
from common.checkpoint import CheckpointManager
from common.sessao import SessaoManager
from common.utils import DIR_RESULT

SERVICE_DIR = Path(__file__).parent
RESULT_DIR = DIR_RESULT / "cautelares_get_info"
CONTROLE_PATH = SERVICE_DIR / "processos_claude_code.json"


# ═══════════════════════════════════════════════════════════════════
#  PIPELINE NOVO: Claude Code lê markdowns e extrai
# ═══════════════════════════════════════════════════════════════════

def carregar_controle() -> dict:
    if CONTROLE_PATH.exists():
        try:
            return json.loads(CONTROLE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "atualizado_em": datetime.now().isoformat(),
        "total_extraidos": 0,
        "processos": {},
    }


def cmd_fila_extracao(args):
    """Gera fila de extração via Claude Code."""
    from services.cautelares_get_info.scripts.fila_extracao import gerar_fila
    from common.utils import DIR_TEXTOS

    src = Path(args[0]) if args and not args[0].startswith("--") else DIR_TEXTOS
    filtro = "*"
    forcar = "--forcar" in args
    for a in args:
        if a.startswith("--filtro="):
            filtro = a.split("=", 1)[1]

    gerar_fila(src, filtro, forcar)


def cmd_status_extracao(args):
    """Mostra progresso granular: por CMD e por processo."""
    fila_path = SERVICE_DIR / "fila_extracao.json"
    ck_path = SERVICE_DIR / "checkpoint_extracao.json"

    if not fila_path.exists():
        print("\n  Fila não gerada. Rode: python run.py cautelares fila-extracao\n")
        return

    fila = json.loads(fila_path.read_text(encoding="utf-8"))
    ck = json.loads(ck_path.read_text(encoding="utf-8")) if ck_path.exists() else {
        "comandos_concluidos": [], "comandos_parciais": {}
    }
    controle = carregar_controle()
    extraidos = set(controle.get("processos", {}).keys())

    total_cmd = fila.get("total_comandos", 0)
    total_proc = fila.get("total_processos", 0)
    done_cmd = len(ck.get("comandos_concluidos", []))
    parc_cmd = len(ck.get("comandos_parciais", {}))

    # Conta processos extraídos da fila atual
    procs_da_fila = []
    for c in fila.get("comandos", []):
        procs_da_fila.extend(c.get("processos", []))
    done_proc = sum(1 for p in procs_da_fila if p in extraidos)

    pct = done_proc / total_proc * 100 if total_proc else 0
    bar = "#" * int(pct // 2.5) + "-" * (40 - int(pct // 2.5))

    print(f"\n  ── Status da extração ──")
    print(f"  [{bar}] {pct:.1f}%")
    print(f"  Comandos:  {done_cmd}/{total_cmd} concluídos | {parc_cmd} parciais")
    print(f"  Processos: {done_proc}/{total_proc} extraídos")
    print(f"  Total geral no controle: {len(extraidos)} processos")

    if ck.get("comandos_parciais"):
        print(f"\n  ── CMDs parciais (alguns processos faltam) ──")
        for num_str, info in sorted(ck["comandos_parciais"].items(), key=lambda x: int(x[0])):
            num = int(num_str)
            print(f"  CMD {num:03d}: {len(info['feitos'])} feitos / "
                  f"{len(info['pendentes'])} pendentes")

    if done_cmd + parc_cmd < total_cmd:
        proximo = done_cmd + 1
        print(f"\n  Próximo CMD pendente: ~{proximo:03d}")
        print(f"  Retomar com: python auto_extrair_cautelares.py")
    else:
        print(f"\n  ✓ Extração completa!")
    print()


def cmd_marcar_extracao(args):
    """Marca CMD como concluído manualmente."""
    if not args:
        print("  USO: marcar-extracao <NUM> [PROCESSOS...]")
        return

    ck_path = SERVICE_DIR / "checkpoint_extracao.json"
    ck = json.loads(ck_path.read_text(encoding="utf-8")) if ck_path.exists() else {
        "criado_em": datetime.now().isoformat(),
        "comandos_concluidos": [],
        "comandos_parciais": {},
        "ultimo_comando": 0,
    }

    num = int(args[0])
    if num not in ck.get("comandos_concluidos", []):
        ck.setdefault("comandos_concluidos", []).append(num)
        ck["comandos_concluidos"].sort()
    if num > ck.get("ultimo_comando", 0):
        ck["ultimo_comando"] = num
    ck.get("comandos_parciais", {}).pop(str(num), None)
    ck["ultima_atualizacao"] = datetime.now().isoformat()
    ck_path.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ CMD #{num:03d} marcado como concluído")


def cmd_consolidar_extracao(args):
    """Lê JSONs do Claude Code e gera planilha xlsx."""
    from services.cautelares_get_info.scripts.consolidar_extracao import consolidar
    consolidar()


def cmd_reset_extracao(args):
    """Limpa fila + checkpoint (NÃO apaga JSONs nem controle de processos)."""
    arquivos = [
        SERVICE_DIR / "fila_extracao.json",
        SERVICE_DIR / "comandos_extracao.txt",
        SERVICE_DIR / "checkpoint_extracao.json",
    ]
    for f in arquivos:
        if f.exists():
            f.unlink()
            print(f"  Removido: {f.name}")
    print(f"\n  ✓ Reset OK (fila + checkpoint).")
    print(f"     PRESERVADOS:")
    print(f"     - resultados/extracao/*.json (dados extraídos)")
    print(f"     - processos_claude_code.json (controle de retomada)")
    print(f"\n     Para zerar TUDO: rode também 'limpar-controle' e apague resultados/extracao/")


def cmd_limpar_controle(args):
    """Zera o processos_claude_code.json — usar com cuidado!"""
    if "--confirmar" not in args:
        print("\n  ⚠️  Esta ação zera o controle de retomada.")
        print(f"     Próxima geração de fila vai considerar TODOS os")
        print(f"     processos como pendentes.")
        print(f"\n     Para confirmar: python run.py cautelares limpar-controle --confirmar\n")
        return

    if CONTROLE_PATH.exists():
        backup = SERVICE_DIR / f"processos_claude_code.bkp_{datetime.now():%Y%m%d_%H%M%S}.json"
        CONTROLE_PATH.rename(backup)
        print(f"  ✓ Backup salvo em: {backup.name}")
    print(f"  ✓ Controle zerado.")


# ═══════════════════════════════════════════════════════════════════
#  PIPELINE ANTIGO (compat)
# ═══════════════════════════════════════════════════════════════════

class FilaCustodiados(FilaBase):
    SERVICE_NAME = "cautelares_get_info"
    BATCH_COM_PDF = 3
    BATCH_SEM_PDF = 10

    def _prompt_default(self):
        return "prompt_custodiado.md"

    def _prompt(self, cl):
        return "prompt_custodiado.md"

    def gerar_comando_com_pdf(self, n, procs, prompt):
        arqs = "\n".join(
            f"  - textos_extraidos/{p['txt_arquivo']}  ({p['numero']} | {p['classe']})"
            for p in procs
        )
        nums = " ".join(p["numero"] for p in procs)
        return f"""# === COMANDO {n:03d} === [CUSTODIADO] [{len(procs)} com PDF] ===
# Processos: {nums}
# Ao concluir: python run.py cautelares marcar {n} {nums}

Leia services/cautelares_get_info/prompts/{prompt}. Extraia dados de cada .md:

{arqs}

Salve em services/cautelares_get_info/resultados/custodiado_{n:03d}.json"""

    def gerar_comando_sem_pdf(self, n, procs, prompt):
        tab = "| Número | Classe | Assunto |\n|---|---|---|\n"
        tab += "\n".join(
            f"| {p['numero']} | {p['classe']} | {p['assunto']} |" for p in procs
        )
        nums = " ".join(p["numero"] for p in procs)
        return f"""# === COMANDO {n:03d} === [CUSTODIADO SEM PDF] ===
# Processos: {nums}

Análise limitada:
{tab}

Salve em services/cautelares_get_info/resultados/custodiado_{n:03d}.json"""


# ═══════════════════════════════════════════════════════════════════
#  Dispatcher
# ═══════════════════════════════════════════════════════════════════

COMANDOS_NOVOS = {
    "fila-extracao": cmd_fila_extracao,
    "status-extracao": cmd_status_extracao,
    "marcar-extracao": cmd_marcar_extracao,
    "consolidar-extracao": cmd_consolidar_extracao,
    "reset-extracao": cmd_reset_extracao,
    "limpar-controle": cmd_limpar_controle,
}


def executar(comando: str, args: list | None = None):
    args = args or []

    if comando in COMANDOS_NOVOS:
        COMANDOS_NOVOS[comando](args)
        return

    # ── Pipeline antigo ──
    if comando == "fila":
        FilaCustodiados(SERVICE_DIR).gerar()
    elif comando == "status":
        FilaCustodiados(SERVICE_DIR).status()
    elif comando == "analisar":
        SessaoManager(SERVICE_DIR / "checkpoint.json").inicio()
        print(f"  Cole comandos de: {SERVICE_DIR / 'comandos_claude_code.txt'}")
    elif comando == "pausa":
        SessaoManager(SERVICE_DIR / "checkpoint.json").fim(SERVICE_DIR / "fila.json")
    elif comando == "marcar":
        if not args:
            print("  USO: marcar <NUM> [PROCESSOS...]")
            return
        CheckpointManager(SERVICE_DIR / "checkpoint.json").marcar_concluido(
            int(args[0]), args[1:],
            f"resultados/custodiado_{int(args[0]):03d}.json",
        )
    elif comando == "consolidar":
        from services.cautelares_get_info.scripts.consolidar import consolidar
        from common.utils import DIR_FILES
        json_dir = Path(__file__).parent.parent.parent / "pre_extraido"
        lista = DIR_FILES / "lista_cadastro_scc.xlsx"
        saida = RESULT_DIR / "cadastro_inicial.xlsx"
        consolidar(json_dir, lista if lista.exists() else None, saida)
    elif comando == "reset":
        CheckpointManager(SERVICE_DIR / "checkpoint.json").reset()
        for f in [SERVICE_DIR / "fila.json", SERVICE_DIR / "comandos_claude_code.txt"]:
            if f.exists():
                f.unlink()
        print("  ✓ Reset OK (pipeline antigo).")

    else:
        print(f"\n  Comando desconhecido: {comando}\n")
        print(f"  ── Pipeline NOVO (Claude Code lê markdowns) ──")
        print(f"    fila-extracao         Gera fila de comandos batch")
        print(f"    status-extracao       Progresso granular (CMD + processo)")
        print(f"    consolidar-extracao   Gera planilha xlsx final")
        print(f"    marcar-extracao       Marca CMD manualmente")
        print(f"    reset-extracao        Zera fila + checkpoint (mantém dados)")
        print(f"    limpar-controle       Zera processos_claude_code.json")
        print()
        print(f"  ── Pipeline ANTIGO (compat) ──")
        print(f"    fila, status, analisar, pausa, marcar, consolidar, reset")
        print()
        print(f"  ── Workflow ──")
        print(f"    1. python run.py cautelares fila-extracao")
        print(f"    2. python auto_extrair_cautelares.py")
        print(f"    3. python run.py cautelares consolidar-extracao")
        print()
