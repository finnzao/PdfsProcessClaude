import sys
from pathlib import Path
from collections import Counter

# Adicionar raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.fila_base import FilaBase
from common.consolidar_base import ConsolidarBase
from common.checkpoint import CheckpointManager
from common.sessao import SessaoManager
from common.utils import DIR_RESULT


SERVICE_DIR = Path(__file__).parent
RESULT_DIR = DIR_RESULT / "analisar_processo"


# ============================================================
# FILA DE ANÁLISE JURÍDICA
# ============================================================
class FilaAnalise(FilaBase):
    SERVICE_NAME = "analisar_processo"
    BATCH_COM_PDF = 3
    BATCH_SEM_PDF = 15

    CLASSE_PARA_PROMPT = {
        "APOrd": "prompt_APOrd.md",
        "IP": "prompt_IP.md",
        "TCO": "prompt_TCO.md",
        "Juri": "prompt_Juri.md",
        "APSum": "prompt_APSum.md",
        "APSumss": "prompt_APSumss.md",
    }

    def gerar_comando_com_pdf(self, cmd_num, processos, prompt_file):
        arquivos = "\n".join(
            f"  - textos_extraidos/{p['txt_arquivo']}"
            f"  ({p['numero']} | {p['assunto']} | {p['dias_parado']}d | {p['urgencia']})"
            for p in processos
        )
        nums = " ".join(p["numero"] for p in processos)
        service_path = f"services/analisar_processo"

        return f"""# === COMANDO {cmd_num:03d} === [{processos[0]['classe']}] [{len(processos)} com PDF] ===
# Processos: {nums}
# Ao concluir: python run.py analise marcar {cmd_num} {nums}

Leia o prompt em {service_path}/prompts/{prompt_file}.
Analise os processos (leia CADA .txt completo):

{arquivos}

Para CADA processo: resumo com páginas, fase processual, diagnóstico,
próximo ato, modelo de despacho, fundamentação legal, prescrição.
Salve em {service_path}/resultados/analise_{cmd_num:03d}.csv"""

    def gerar_comando_sem_pdf(self, cmd_num, processos, prompt_file):
        tabela = "| Número | Classe | Assunto | Tarefa | Dias | Última Mov. |\n"
        tabela += "|--------|--------|---------|--------|------|------------|\n"
        for p in processos:
            tabela += (f"| {p['numero']} | {p['classe']} | {p['assunto']} "
                       f"| {p['tarefa'][:30]} | {p['dias_parado']} | {p['ultima_mov'][:40]} |\n")
        nums = " ".join(p["numero"] for p in processos)
        service_path = f"services/analisar_processo"

        return f"""# === COMANDO {cmd_num:03d} === [{processos[0]['classe']}] [{len(processos)} SEM PDF] ===
# Processos: {nums}
# Ao concluir: python run.py analise marcar {cmd_num} {nums}

Leia {service_path}/prompts/{prompt_file}.
Analise com base APENAS nos dados do CSV:

{tabela}

Análise LIMITADA. Salve em {service_path}/resultados/analise_{cmd_num:03d}.csv"""


# ============================================================
# CONSOLIDAÇÃO
# ============================================================
class ConsolidarAnalise(ConsolidarBase):
    SERVICE_NAME = "analisar_processo"

    def consolidar(self):
        print("=" * 60)
        print("  CONSOLIDAÇÃO — Análise Jurídica")
        print("=" * 60)

        ordem_urgencia = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2, "BAIXA": 3}
        saida = self.consolidar_csvs(
            pattern="analise_*.csv",
            saida_nome="relatorio_final.csv",
            ordenar_por=lambda x: (
                ordem_urgencia.get(x.get("urgencia", "BAIXA"), 4),
                -int(x.get("dias_parado", 0)) if x.get("dias_parado", "").isdigit() else 0
            )
        )
        if saida:
            print(f"\n  ✅ Relatório: {saida}")


# ============================================================
# INTERFACE
# ============================================================
def executar(comando, args=None):
    args = args or []

    if comando == "fila":
        print("=" * 60)
        print("  GERAR FILA — Análise Jurídica")
        print("=" * 60)
        fila = FilaAnalise(SERVICE_DIR)
        fila.gerar()

    elif comando == "status":
        print("=" * 60)
        print("  STATUS — Análise Jurídica")
        print("=" * 60)
        fila = FilaAnalise(SERVICE_DIR)
        fila.status()

    elif comando == "analisar":
        sm = SessaoManager(SERVICE_DIR / "checkpoint.json")
        sm.inicio()
        print("  Abra comandos_claude_code.txt e cole os comandos no Claude Code.")
        print(f"  Arquivo: {SERVICE_DIR / 'comandos_claude_code.txt'}")

    elif comando == "pausa":
        sm = SessaoManager(SERVICE_DIR / "checkpoint.json")
        sm.fim(SERVICE_DIR / "fila.json")

    elif comando == "marcar":
        if len(args) < 1:
            print("  USO: python run.py analise marcar <NUM> [PROCESSOS...]")
            return
        cm = CheckpointManager(SERVICE_DIR / "checkpoint.json")
        cmd_num = int(args[0])
        processos = args[1:]
        cm.marcar_concluido(cmd_num, processos,
                            f"resultados/analise_{cmd_num:03d}.csv")

    elif comando == "consolidar":
        c = ConsolidarAnalise(SERVICE_DIR, RESULT_DIR)
        c.consolidar()

    elif comando == "reset":
        cm = CheckpointManager(SERVICE_DIR / "checkpoint.json")
        cm.reset()
        for f in [SERVICE_DIR / "fila.json", SERVICE_DIR / "comandos_claude_code.txt"]:
            if f.exists():
                f.unlink()
        print("  Reset completo.")

    else:
        print(f"  Comando desconhecido: {comando}")
        print("  Disponíveis: fila, status, analisar, pausa, marcar, consolidar, reset")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("USO: python -m services.analisar_processo.main <comando>")
        sys.exit(1)
    executar(sys.argv[1], sys.argv[2:])
