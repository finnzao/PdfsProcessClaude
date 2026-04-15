import sys, re, json, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.fila_base import FilaBase
from common.checkpoint import CheckpointManager
from common.sessao import SessaoManager
from common.formato_saida import instrucao_para_comando
from common.consolidar_analise import ConsolidarAnalise
from common.utils import DIR_RESULT

SERVICE_DIR = Path(__file__).parent
RESULT_DIR = DIR_RESULT / "analisar_processo"
ANALISES_DIR = SERVICE_DIR / "resultados" / "analises"
ANALISES_DIR.mkdir(parents=True, exist_ok=True)

# ── Rotas de leitura por classe processual ──

ROTA_BASE = {
    "APOrd": [
        "knowledge/processual/ritos_processuais.md (secao APOrd)",
        "knowledge/criminal/prescricao.md",
        "knowledge/modelos/despachos.md",
    ],
    "IP": [
        "knowledge/processual/ritos_processuais.md (secao IP)",
        "knowledge/criminal/prescricao.md",
        "knowledge/modelos/despachos.md",
    ],
    "TCO": [
        "knowledge/processual/ritos_processuais.md (secao Sumarissima)",
        "knowledge/criminal/prescricao.md",
        "knowledge/modelos/despachos.md",
    ],
    "Juri": [
        "knowledge/processual/ritos_processuais.md (secao Juri)",
        "knowledge/criminal/prescricao.md",
        "knowledge/criminal/crimes_pessoa.md (secao Homicidio)",
        "knowledge/modelos/decisoes.md",
        "knowledge/modelos/despachos.md",
    ],
    "APSum": [
        "knowledge/processual/ritos_processuais.md (secao APSum)",
        "knowledge/criminal/prescricao.md",
        "knowledge/modelos/despachos.md",
    ],
    "APSumss": [
        "knowledge/processual/ritos_processuais.md (secao Sumarissima)",
        "knowledge/criminal/prescricao.md",
        "knowledge/modelos/despachos.md",
    ],
}

ROTA_DEFAULT = [
    "knowledge/processual/ritos_processuais.md",
    "knowledge/criminal/prescricao.md",
    "knowledge/modelos/despachos.md",
    "knowledge/processual/competencia.md",
]

KEYWORDS_LEIS = [
    (r"tráfico|drogas|entorpecente|cocaína|maconha|crack", "knowledge/leis/drogas.md"),
    (r"violência doméstica|maria da penha|mulher|protetiva|VD", "knowledge/leis/maria_penha.md"),
    (r"arma|porte ilegal|posse.*arma|munição|desarmamento", "knowledge/leis/armas.md"),
    (r"trânsito|embriaguez|CTB|volante|atropelamento", "knowledge/leis/transito.md"),
    (r"peculato|corrupção|concussão|prevaricação|funcionário", "knowledge/leis/adm_publica.md"),
    (r"organização criminosa|facção|associação criminosa", "knowledge/criminal/organizacao_criminosa.md"),
    (r"homicídio|feminicídio|lesão corporal|estupro|cárcere", "knowledge/criminal/crimes_pessoa.md"),
    (r"roubo|furto|latrocínio|extorsão|estelionato|receptação", "knowledge/criminal/crimes_patrimonio.md"),
]


def _detectar_extras(assunto):
    extras = []
    for pattern, arquivo in KEYWORDS_LEIS:
        if re.search(pattern, assunto, re.IGNORECASE):
            extras.append(arquivo)
    return extras


def _montar_rota(classe, assunto):
    base = list(ROTA_BASE.get(classe, ROTA_DEFAULT))
    extras = _detectar_extras(assunto)
    vistos = set()
    rota = []
    for arq in base + extras:
        nome = arq.split(" (")[0]
        if nome not in vistos:
            vistos.add(nome)
            rota.append(arq)
    return rota


def _fmt_rota(rota):
    return "\n".join(f"  {i}. {arq}" for i, arq in enumerate(rota, 1))


class FilaAnalise(FilaBase):
    SERVICE_NAME = "analisar_processo"
    BATCH_COM_PDF = 3
    BATCH_SEM_PDF = 15
    CLASSE_PARA_PROMPT = {
        "APOrd": "prompt_APOrd.md", "IP": "prompt_IP.md", "TCO": "prompt_TCO.md",
        "Juri": "prompt_Juri.md", "APSum": "prompt_APSum.md", "APSumss": "prompt_APSumss.md",
    }

    def gerar_comando_com_pdf(self, n, procs, prompt):
        arqs = " ".join(f"textos_extraidos/{p['txt_arquivo']}" for p in procs)
        nums = " ".join(p["numero"] for p in procs)
        resumo = "\n".join(
            f"  {p['numero']} | {p['assunto']} | {p['dias_parado']}d | {p['urgencia']}"
            for p in procs
        )
        assuntos = " ".join(p.get("assunto", "") for p in procs)
        rota = _fmt_rota(_montar_rota(procs[0]["classe"], assuntos))
        instrucao = instrucao_para_comando(n)

        return f"""# === CMD {n:03d} [{procs[0]['classe']}] [{len(procs)} procs] ===
# Ao concluir: python run.py analise marcar {n} {nums}

Leia services/analisar_processo/prompts/{prompt}

Rota de leitura:
{rota}
  +reu preso -> knowledge/processual/cautelares_e_prisao.md
  +recurso pendente -> knowledge/processual/recursos.md
  +minutar sentenca -> knowledge/criminal/dosimetria.md + knowledge/modelos/sentencas.md

Processos:
{resumo}

Arquivos: {arqs}
{instrucao}"""

    def gerar_comando_sem_pdf(self, n, procs, prompt):
        tab = "| Numero | Classe | Assunto | Dias | Ultima Mov. |\n|---|---|---|---|---|\n"
        tab += "\n".join(
            f"| {p['numero']} | {p['classe']} | {p['assunto']} | {p['dias_parado']} | {p['ultima_mov'][:40]} |"
            for p in procs
        )
        nums = " ".join(p["numero"] for p in procs)
        assuntos = " ".join(p.get("assunto", "") for p in procs)
        rota = _fmt_rota(_montar_rota(procs[0]["classe"], assuntos))
        instrucao = instrucao_para_comando(n)

        return f"""# === CMD {n:03d} [{procs[0]['classe']}] [{len(procs)} SEM PDF] ===
# Ao concluir: python run.py analise marcar {n} {nums}

Leia services/analisar_processo/prompts/{prompt}

Rota de leitura:
{rota}

Analise LIMITADA (sem PDF):

{tab}
{instrucao}"""


def executar(comando, args=None):
    args = args or []

    if comando == "fila":
        # Aceita: fila TCO | fila TCO IP | fila TCO,IP | fila TCO+IP
        FilaAnalise(SERVICE_DIR).gerar(filtro_classe=args if args else None)

    elif comando == "status":
        FilaAnalise(SERVICE_DIR).status()

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
            int(args[0]), args[1:], f"resultados/triagem_{int(args[0]):03d}.json"
        )

    elif comando == "consolidar":
        ConsolidarAnalise(SERVICE_DIR, RESULT_DIR).consolidar()

    elif comando == "reset":
        CheckpointManager(SERVICE_DIR / "checkpoint.json").reset()
        for f in [SERVICE_DIR / "fila.json", SERVICE_DIR / "comandos_claude_code.txt"]:
            if f.exists():
                f.unlink()
        # Limpar filas filtradas também
        for f in SERVICE_DIR.glob("fila_*.json"):
            f.unlink()
        for f in SERVICE_DIR.glob("comandos_claude_code_*.txt"):
            f.unlink()
        print("  Reset OK.")

    else:
        print(f"  Comando desconhecido: {comando}")
        print(f"  Disponíveis: fila [CLASSES], status, analisar, pausa, marcar, consolidar, reset")
        print(f"  Classes: TCO, IP, APOrd, APSum, APSumss, Juri")
        print(f"  Exemplos:")
        print(f"    python run.py analise fila TCO         # só TCO")
        print(f"    python run.py analise fila TCO IP      # TCO e IP")
        print(f"    python run.py analise fila TCO,IP,Juri # TCO, IP e Júri")
