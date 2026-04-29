"""
utils/constantes_pje.py — Padrões para limpeza de textos extraídos do PJe/TJBA.

Concentra tudo que é "ruído" em PDFs do PJe: cabeçalhos de assinatura digital,
URLs, IPs, rodapés institucionais (TJBA, Sinesp, Polícia Civil) e identificadores
de documento (Num. XXXXX - Pág. X).

Como adicionar novo padrão:
    1. Crie a re.compile(...) na lista PADROES_LIXO
    2. Teste com um PDF representativo
    3. Mantenha re.IGNORECASE quando relevante
"""

import re


# ═══════════════════════════════════════════════════════════════════
#  Identificadores de documento PJe
# ═══════════════════════════════════════════════════════════════════
# O PJe imprime no rodapé de cada página algo como:
#   "Num. 440866922 - Pág. 1"
# Capturamos isso ANTES de limpar para preservar a rastreabilidade.

RE_NUM_PAG = re.compile(r'Num[.\s]+(\d{5,})\s*[-–]\s*P[áa]g[.\s]+(\d+)')
RE_NUM_ONLY = re.compile(r'Num[.\s]+(\d{5,})')


def extrair_doc_id(texto: str) -> tuple | None:
    """
    Extrai (num_documento, num_pagina) do rodapé PJe.
    Retorna o ÚLTIMO match (rodapé fica no final da página).

    >>> extrair_doc_id("...texto... Num. 440866922 - Pág. 3")
    ('440866922', '3')
    """
    matches = RE_NUM_PAG.findall(texto)
    if matches:
        return matches[-1]
    matches_simples = RE_NUM_ONLY.findall(texto)
    if matches_simples:
        return (matches_simples[-1], "1")
    return None


# ═══════════════════════════════════════════════════════════════════
#  Padrões de lixo institucional
# ═══════════════════════════════════════════════════════════════════
# Cada padrão é uma re.compile pré-compilada. A ordem importa:
# padrões mais específicos primeiro, mais genéricos depois.

PADROES_LIXO = [
    # ── Cabeçalhos de geração/assinatura PJe ──
    re.compile(r'Este documento foi gerado pelo usu.rio.*?(?=\n|$)', re.I),
    re.compile(r'N[úu]mero do documento:\s*\d+.*?(?=\n|$)', re.I),
    re.compile(r'Assinado eletronicamente.*?(?=\n|$)', re.I),
    re.compile(r'Documento assinado eletronicamente.*?Bras[íi]lia\.?', re.I | re.DOTALL),
    re.compile(r'\(documento gerado e assinado automaticamente pelo PJe\)', re.I),
    re.compile(r'C[óo]digo Verificador \(MAC\).*?(?=\n|$)', re.I),
    re.compile(r'A autenticidade do documento.*?(?=\n\n|\Z)', re.I | re.DOTALL),
    re.compile(r'Informe o c[óo]digo verificador.*?(?=\n|$)', re.I),
    re.compile(r'Este documento ainda poder[áa].*?(?=\n|$)', re.I),

    # ── URLs e identificadores genéricos ──
    re.compile(r'https?://\S+', re.I),
    re.compile(r'IP de Registro:.*?(?=\n|$)', re.I),

    # ── Identificadores do PJe (já capturados em extrair_doc_id) ──
    re.compile(r'Num[.\s]+\d{5,}\s*[-–]\s*P[áa]g[.\s]+\d+', re.I),

    # ── Marcadores de página/folha ──
    re.compile(r'Pg\.\s*\d+/\d+', re.I),
    re.compile(r'P[áa]gina\s+\d+\s+de\s+\d+', re.I),
    re.compile(r'Fls:?\s*\d*\s*\n?\s*Visto:?', re.I),
    re.compile(r'Impresso por:.*?(?=\n|$)', re.I),
    re.compile(r'Data de Impress[ãa]o:.*?(?=\n|$)', re.I),

    # ── Rodapés Sinesp ──
    re.compile(r'PPe\s*[-–]\s*Procedimentos Policiais.*?(?=\n|$)', re.I),
    re.compile(r'Gerado por Sinesp Seguran[çc]a', re.I),
    re.compile(r'O sigilo deste documento.*?administrativas\.?', re.I | re.DOTALL),

    # ── Cabeçalhos institucionais ──
    re.compile(r'Minist[ée]rio da\s*\n?\s*Justi[çc]a e Seguran[çc]a P[úu]blica', re.I),
    re.compile(r'Secretaria Nacional de\s*\n?\s*Seguran[çc]a P[úu]blica', re.I),
    re.compile(r'TJBA\s*\n?\s*PJe\s*[-–]\s*Processo Judicial.*', re.I),
    re.compile(
        r'GOVERNO DO ESTADO DA BAHIA\s*\n?\s*POL[ÍI]CIA CIVIL\s*\n?'
        r'\s*DELEGACIA TERRITORIAL\s*[-–].*?[-–]\s*BA\s*\n?',
        re.I,
    ),
    re.compile(r'GOVERNO DO ESTADO DE SERGIPE\s*\n?\s*POL[ÍI]CIA CIVIL.*?\n', re.I),
    re.compile(r'GOVERNO DO ESTADO DA BAHIA\s*\n?\s*DELEGACIA TERRITORIAL.*?\n', re.I),
    re.compile(r'ESTADO DA BAHIA\s*\n?\s*SECRETARIA DA SEGURAN.A P.BLICA.*?\n', re.I),
    re.compile(r'PODER JUDICI.RIO[\s\n]+TRIBUNAL DE JUSTI.A DO ESTADO DA BAHIA[\s\n]*', re.I),
    re.compile(r'Autos n[°º]\s*[\d.\-/]+\s*\n?', re.I),

    # ── Imagens/markdown residual ──
    re.compile(r'!\[.*?\]\(.*?\)', re.I),

    # ── Linhas só com números longos (códigos de barra/protocolo) ──
    re.compile(r'^\d{10,}\s*$', re.I | re.M),
]


def limpar_texto(texto: str) -> str:
    """
    Remove cabeçalhos, assinaturas e lixo institucional do texto.
    Aplica todos os PADROES_LIXO em ordem e normaliza espaços/quebras.

    >>> limpar_texto("Algo útil\\nNum. 12345 - Pág. 1\\nMais texto")
    'Algo útil\\nMais texto'
    """
    for padrao in PADROES_LIXO:
        texto = padrao.sub('', texto)

    # Normalizações finais
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    texto = re.sub(r'[ \t]+\n', '\n', texto)
    texto = re.sub(r'\n\|[\s|]*\|\n', '\n', texto)
    return texto.strip()
