"""services/analisar_processo/main.py — Helpers de selecao e carregamento de prompts."""

import re
from pathlib import Path

ROOT = Path(__file__).parent
DIR_PROMPTS = ROOT / "prompts"


# Mapeamento canonico de chaves -> arquivo de prompt
PROMPTS_DISPONIVEIS = {
    "APOrd": "prompt_APOrd.md",     # Acao penal ordinaria
    "APSum": "prompt_APSum.md",     # Sumaria
    "APSumss": "prompt_APSumss.md", # Sumarissima (JECrim)
    "IP": "prompt_IP.md",           # Inquerito policial
    "Juri": "prompt_Juri.md",       # Tribunal do juri
    "TCO": "prompt_TCO.md",         # Termo circunstanciado
    "outros": "prompt_outros.md",
}


def carregar_prompt(chave: str) -> str:
    """Le um prompt do diretorio prompts/. Retorna conteudo ou string vazia."""
    nome_arq = PROMPTS_DISPONIVEIS.get(chave)
    if not nome_arq:
        return ""
    p = DIR_PROMPTS / nome_arq
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


# Regex de classe -> chave canonica do prompt
_REGEX_CLASSE_PARA_CHAVE = [
    (re.compile(r"termo\s+circunstanciado|t\.?c\.?o\.?", re.I), "TCO"),
    (re.compile(r"in[qu]u[ée]rito\s+policial|\bIPL?\b", re.I), "IP"),
    (re.compile(r"tribunal\s+do\s+j[uú]ri|j[uú]ri", re.I), "Juri"),
    (re.compile(r"sumar[ií]ssim[ao]|jecrim|juizado\s+especial\s+criminal", re.I), "APSumss"),
    (re.compile(r"sum[áa]ri[ao]", re.I), "APSum"),
    (re.compile(r"ordin[áa]ri[ao]|a[çc][ãa]o\s+penal", re.I), "APOrd"),
]


def selecionar_prompt_por_classe(classe: str, assunto: str = "") -> str:
    """
    Decide qual prompt carregar com base no campo Classe (e opcionalmente Assunto).
    Retorna chave canonica (ex.: 'APOrd', 'IP'). Default: 'outros'.
    """
    texto = f"{classe or ''} {assunto or ''}"
    for regex, chave in _REGEX_CLASSE_PARA_CHAVE:
        if regex.search(texto):
            return chave
    return "outros"
