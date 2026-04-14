import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.fila_base import FilaBase
from common.consolidar_base import ConsolidarBase
from common.checkpoint import CheckpointManager
from common.sessao import SessaoManager
from common.utils import DIR_RESULT

SERVICE_DIR = Path(__file__).parent
RESULT_DIR = DIR_RESULT / "analisar_processo"


class FilaAnalise(FilaBase):
    """Gera comandos de análise agrupados por classe processual."""
    SERVICE_NAME = "analisar_processo"
    BATCH_COM_PDF = 3
    BATCH_SEM_PDF = 15
    CLASSE_PARA_PROMPT = {"APOrd":"prompt_APOrd.md","IP":"prompt_IP.md","TCO":"prompt_TCO.md",
        "Juri":"prompt_Juri.md","APSum":"prompt_APSum.md","APSumss":"prompt_APSumss.md"}

    def gerar_comando_com_pdf(self, n, procs, prompt):
        arqs = "\n".join(f"  - textos_extraidos/{p['txt_arquivo']}  ({p['numero']} | {p['assunto']} | {p['dias_parado']}d | {p['urgencia']})" for p in procs)
        nums = " ".join(p["numero"] for p in procs)
        return f"""# === COMANDO {n:03d} === [{procs[0]['classe']}] [{len(procs)} com PDF] ===
# Processos: {nums}
# Ao concluir: python run.py analise marcar {n} {nums}

Leia services/analisar_processo/prompts/{prompt}.
Analise cada .md completo:

{arqs}

Salve em services/analisar_processo/resultados/analise_{n:03d}.csv"""

    def gerar_comando_sem_pdf(self, n, procs, prompt):
        tab = "| Número | Classe | Assunto | Dias | Última Mov. |\n|---|---|---|---|---|\n"
        tab += "\n".join(f"| {p['numero']} | {p['classe']} | {p['assunto']} | {p['dias_parado']} | {p['ultima_mov'][:40]} |" for p in procs)
        nums = " ".join(p["numero"] for p in procs)
        return f"""# === COMANDO {n:03d} === [{procs[0]['classe']}] [{len(procs)} SEM PDF] ===
# Processos: {nums}
# Ao concluir: python run.py analise marcar {n} {nums}

Leia services/analisar_processo/prompts/{prompt}. Análise LIMITADA (sem PDF):

{tab}

Salve em services/analisar_processo/resultados/analise_{n:03d}.csv"""


class ConsolidarAnalise(ConsolidarBase):
    """Junta CSVs ordenados por urgência."""
    SERVICE_NAME = "analisar_processo"
    def consolidar(self):
        print(f"{'='*60}\n  CONSOLIDAÇÃO — Análise Jurídica\n{'='*60}")
        ord_urg = {"CRITICA":0,"ALTA":1,"MEDIA":2,"BAIXA":3}
        s = self.consolidar_csvs("analise_*.csv", "relatorio_final.csv",
            lambda x: (ord_urg.get(x.get("urgencia","BAIXA"),4), -int(x.get("dias_parado",0)) if x.get("dias_parado","").isdigit() else 0))
        if s: print(f"\n  ✅ {s}")


def executar(comando, args=None):
    """Roteador de comandos."""
    args = args or []
    if comando == "fila": FilaAnalise(SERVICE_DIR).gerar()
    elif comando == "status": FilaAnalise(SERVICE_DIR).status()
    elif comando == "analisar":
        SessaoManager(SERVICE_DIR/"checkpoint.json").inicio()
        print(f"  Cole comandos de: {SERVICE_DIR/'comandos_claude_code.txt'}")
    elif comando == "pausa": SessaoManager(SERVICE_DIR/"checkpoint.json").fim(SERVICE_DIR/"fila.json")
    elif comando == "marcar":
        if not args: print("  USO: marcar <NUM> [PROCESSOS...]"); return
        CheckpointManager(SERVICE_DIR/"checkpoint.json").marcar_concluido(int(args[0]), args[1:], f"resultados/analise_{int(args[0]):03d}.csv")
    elif comando == "consolidar": ConsolidarAnalise(SERVICE_DIR, RESULT_DIR).consolidar()
    elif comando == "reset":
        CheckpointManager(SERVICE_DIR/"checkpoint.json").reset()
        for f in [SERVICE_DIR/"fila.json", SERVICE_DIR/"comandos_claude_code.txt"]:
            if f.exists(): f.unlink()
        print("  Reset OK.")
    else: print(f"  Desconhecido: {comando}")
