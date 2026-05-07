"""
common/limpeza_pje.py — Padroes de limpeza para textos do PJe/TJBA.

Remove cabecalhos de assinatura digital, URLs, identificadores PJe e
rodapes institucionais. Mantem extrair_doc_id antes de limpar para
preservar rastreabilidade Num. XXXX - Pag. X.
"""

import re

# ========================================================
#   Identificadores de documento PJe
# ========================================================

RE_NUM_PAG = re.compile(r"Num[.\s]+(\d{5,})\s*[-–]\s*P[áa]g[.\s]+(\d+)")
RE_NUM_ONLY = re.compile(r"Num[.\s]+(\d{5,})")


def extrair_doc_id(texto: str):
    """
    Extrai (num_documento, num_pagina) do rodape PJe.
    Retorna o ULTIMO match (rodape fica no final da pagina).
    """
    matches = RE_NUM_PAG.findall(texto)
    if matches:
        return matches[-1]
    matches_simples = RE_NUM_ONLY.findall(texto)
    if matches_simples:
        return (matches_simples[-1], "1")
    return None


# ========================================================
#   Padroes de lixo institucional
# ========================================================

PADROES_LIXO = [
    # Cabecalhos de geracao/assinatura PJe
    re.compile(r"Este documento foi gerado pelo usu.rio.*?(?=\n|$)", re.I),
    re.compile(r"N[úu]mero do documento:\s*\d+.*?(?=\n|$)", re.I),
    re.compile(r"Assinado eletronicamente.*?(?=\n|$)", re.I),
    re.compile(r"Documento assinado eletronicamente.*?Bras[íi]lia\.?", re.I | re.DOTALL),
    re.compile(r"\(documento gerado e assinado automaticamente pelo PJe\)", re.I),
    re.compile(r"C[óo]digo Verificador \(MAC\).*?(?=\n|$)", re.I),
    re.compile(r"A autenticidade do documento.*?(?=\n\n|\Z)", re.I | re.DOTALL),
    re.compile(r"Informe o c[óo]digo verificador.*?(?=\n|$)", re.I),
    re.compile(r"Este documento ainda poder[áa].*?(?=\n|$)", re.I),

    # URLs e identificadores
    re.compile(r"https?://\S+", re.I),
    re.compile(r"IP de Registro:.*?(?=\n|$)", re.I),

    # Identificadores PJe (capturados antes em extrair_doc_id)
    re.compile(r"Num[.\s]+\d{5,}\s*[-–]\s*P[áa]g[.\s]+\d+", re.I),

    # Marcadores de paginacao
    re.compile(r"Pg\.\s*\d+/\d+", re.I),
    re.compile(r"P[áa]gina\s+\d+\s+de\s+\d+", re.I),
    re.compile(r"Fls:?\s*\d*\s*\n?\s*Visto:?", re.I),
    re.compile(r"Impresso por:.*?(?=\n|$)", re.I),
    re.compile(r"Data de Impress[ãa]o:.*?(?=\n|$)", re.I),

    # Rodapes Sinesp
    re.compile(r"PPe\s*[-–]\s*Procedimentos Policiais.*?(?=\n|$)", re.I),
    re.compile(r"Gerado por Sinesp Seguran[çc]a", re.I),
    re.compile(r"O sigilo deste documento.*?administrativas\.?", re.I | re.DOTALL),

    # Cabecalhos institucionais
    re.compile(r"Minist[ée]rio da\s*\n?\s*Justi[çc]a e Seguran[çc]a P[úu]blica", re.I),
    re.compile(r"Secretaria Nacional de\s*\n?\s*Seguran[çc]a P[úu]blica", re.I),
    re.compile(r"TJBA\s*\n?\s*PJe\s*[-–]\s*Processo Judicial.*", re.I),
    re.compile(
        r"GOVERNO DO ESTADO DA BAHIA\s*\n?\s*POL[ÍI]CIA CIVIL\s*\n?"
        r"\s*DELEGACIA TERRITORIAL\s*[-–].*?[-–]\s*BA\s*\n?",
        re.I,
    ),
    re.compile(r"GOVERNO DO ESTADO DE SERGIPE\s*\n?\s*POL[ÍI]CIA CIVIL.*?\n", re.I),
    re.compile(r"GOVERNO DO ESTADO DA BAHIA\s*\n?\s*DELEGACIA TERRITORIAL.*?\n", re.I),
    re.compile(r"ESTADO DA BAHIA\s*\n?\s*SECRETARIA DA SEGURAN.A P.BLICA.*?\n", re.I),
    re.compile(r"PODER JUDICI.RIO[\s\n]+TRIBUNAL DE JUSTI.A DO ESTADO DA BAHIA[\s\n]*", re.I),
    re.compile(r"Autos n[°º]\s*[\d.\-/]+\s*\n?", re.I),

    # Imagens markdown residual
    re.compile(r"!\[.*?\]\(.*?\)", re.I),

    # Linhas de codigo de barras / protocolo
    re.compile(r"^\d{10,}\s*$", re.I | re.M),
]


def limpar_texto(texto: str) -> str:
    """Remove lixo institucional e normaliza espacos."""
    if not texto:
        return ""
    for padrao in PADROES_LIXO:
        texto = padrao.sub("", texto)

    # Normalizacao final
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    texto = re.sub(r"\n\|[\s|]*\|\n", "\n", texto)
    return texto.strip()
