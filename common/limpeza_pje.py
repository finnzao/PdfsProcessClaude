"""
common/limpeza_pje.py — Padroes de limpeza para textos do PJe/TJBA.

Remove cabecalhos de assinatura digital, URLs, identificadores PJe e
rodapes institucionais. extrair_doc_id roda antes da limpeza para
preservar rastreabilidade Num. XXXX - Pag. X.

Suporta modo verbose para registrar trechos removidos e regex aplicada.
"""

import re
from typing import Optional

# ========================================================
#   Identificadores de documento PJe (preservar doc_id)
# ========================================================

# Padroes ampliados: aceita "Num.", "Documento nº", "Id.", "ID:" etc.
RE_NUM_PAG = re.compile(
    r"(?:Num[.\s]+|Documento\s+n[º°.]?\s*|Id[.\s]+|ID[:\s]+)"
    r"(\d{5,})\s*[-–]\s*P[áa]g[.\s]+(\d+)",
    re.I,
)
RE_NUM_ONLY = re.compile(
    r"(?:Num[.\s]+|Documento\s+n[º°.]?\s*|Id[.\s]+|ID[:\s]+)(\d{5,})",
    re.I,
)


def extrair_doc_id(texto: str):
    """Retorna o ULTIMO (num_doc, pag) — rodape fica no fim da pagina."""
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
# Cada entrada: (nome, regex). Regex evita .* gananciosa: usa lookahead
# para fim de linha e limita escopo com {0,N}.

PADROES_LIXO: list[tuple[str, re.Pattern]] = [
    # Cabecalhos de geracao/assinatura PJe
    ("usuario_gerou", re.compile(r"Este documento foi gerado pelo usu[aá]rio[^\n]{0,200}(?=\n|$)", re.I)),
    ("num_doc_meta", re.compile(r"N[úu]mero do documento:\s*\d+[^\n]{0,150}(?=\n|$)", re.I)),
    ("assinado_elet", re.compile(r"Assinado eletronicamente[^\n]{0,200}(?=\n|$)", re.I)),
    ("doc_assinado_brasilia", re.compile(
        r"Documento assinado eletronicamente[^\n]{0,300}?Bras[íi]lia\.?",
        re.I | re.DOTALL,
    )),
    ("gerado_assinado_pje", re.compile(
        r"\(documento gerado e assinado automaticamente pelo PJe\)", re.I,
    )),
    ("mac", re.compile(r"C[óo]digo Verificador \(MAC\)[^\n]{0,200}(?=\n|$)", re.I)),
    ("autenticidade", re.compile(
        r"A autenticidade do documento[^\n]{0,500}?(?=\n\n|\Z)",
        re.I | re.DOTALL,
    )),
    ("informe_verificador", re.compile(
        r"Informe o c[óo]digo verificador[^\n]{0,200}(?=\n|$)", re.I,
    )),
    ("ainda_podera", re.compile(r"Este documento ainda poder[áa][^\n]{0,200}(?=\n|$)", re.I)),

    # URLs e identificadores
    ("url", re.compile(r"https?://\S+", re.I)),
    ("ip_registro", re.compile(r"IP de Registro:[^\n]{0,80}(?=\n|$)", re.I)),

    # Identificadores PJe (ja capturados em extrair_doc_id)
    ("num_pag_rodape", re.compile(
        r"(?:Num[.\s]+|Documento\s+n[º°.]?\s*|Id[.\s]+|ID[:\s]+)\d{5,}\s*[-–]\s*P[áa]g[.\s]+\d+",
        re.I,
    )),

    # Paginacao
    ("pg_total", re.compile(r"Pg\.\s*\d+/\d+", re.I)),
    ("pag_de", re.compile(r"P[áa]gina\s+\d+\s+de\s+\d+", re.I)),
    ("fls_visto", re.compile(r"Fls:?\s*\d*\s*\n?\s*Visto:?", re.I)),
    ("impresso_por", re.compile(r"Impresso por:[^\n]{0,150}(?=\n|$)", re.I)),
    ("data_impressao", re.compile(r"Data de Impress[ãa]o:[^\n]{0,80}(?=\n|$)", re.I)),

    # Rodapes Sinesp
    ("ppe", re.compile(r"PPe\s*[-–]\s*Procedimentos Policiais[^\n]{0,200}(?=\n|$)", re.I)),
    ("sinesp", re.compile(r"Gerado por Sinesp Seguran[çc]a", re.I)),
    ("sigilo_admin", re.compile(
        r"O sigilo deste documento[^\n]{0,500}?administrativas\.?",
        re.I | re.DOTALL,
    )),

    # Cabecalhos institucionais (limites explicitos)
    ("min_justica", re.compile(
        r"Minist[ée]rio da\s*\n?\s*Justi[çc]a e Seguran[çc]a P[úu]blica", re.I,
    )),
    ("senasp", re.compile(
        r"Secretaria Nacional de\s*\n?\s*Seguran[çc]a P[úu]blica", re.I,
    )),
    ("tjba_pje", re.compile(r"TJBA\s*\n?\s*PJe\s*[-–]\s*Processo Judicial[^\n]{0,150}", re.I)),
    ("delegacia_ba", re.compile(
        r"GOVERNO DO ESTADO DA BAHIA\s*\n?\s*POL[ÍI]CIA CIVIL\s*\n?"
        r"\s*DELEGACIA TERRITORIAL\s*[-–][^\n]{0,200}[-–]\s*BA\s*\n?",
        re.I,
    )),
    ("delegacia_se", re.compile(
        r"GOVERNO DO ESTADO DE SERGIPE\s*\n?\s*POL[ÍI]CIA CIVIL[^\n]{0,150}\n", re.I,
    )),
    ("delegacia_ba_curto", re.compile(
        r"GOVERNO DO ESTADO DA BAHIA\s*\n?\s*DELEGACIA TERRITORIAL[^\n]{0,200}\n", re.I,
    )),
    ("seguranca_ba", re.compile(
        r"ESTADO DA BAHIA\s*\n?\s*SECRETARIA DA SEGURAN[CÇ]A P[ÚU]BLICA[^\n]{0,200}\n", re.I,
    )),
    ("poder_judiciario", re.compile(
        r"PODER JUDICI[ÁA]RIO[\s\n]+TRIBUNAL DE JUSTI[ÇC]A DO ESTADO DA BAHIA[\s\n]*", re.I,
    )),
    ("autos_n", re.compile(r"Autos n[°º]\s*[\d.\-/]+\s*\n?", re.I)),

    # Imagens markdown residual
    ("imagem_md", re.compile(r"!\[[^\]]{0,200}\]\([^)]{0,300}\)", re.I)),

    # Linhas de codigo de barras / protocolo (10+ digitos sozinhos)
    ("codigo_barras", re.compile(r"^\d{10,}\s*$", re.I | re.M)),
]


# ========================================================
#   Funcao principal
# ========================================================

def limpar_texto(
    texto: str,
    verbose: bool = False,
    debug_log: Optional[list] = None,
) -> str:
    """
    Remove lixo institucional e normaliza espacos.

    verbose: se True e debug_log fornecido, registra cada match removido.
    debug_log: lista que recebe dicts {padrao, trecho, posicao}.
    """
    if not texto:
        return ""

    for nome, padrao in PADROES_LIXO:
        if verbose and debug_log is not None:
            for m in padrao.finditer(texto):
                debug_log.append({
                    "padrao": nome,
                    "trecho": m.group(0)[:120],
                    "posicao": m.start(),
                })
        texto = padrao.sub("", texto)

    # Normalizacao final
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    texto = re.sub(r"\n\|[\s|]*\|\n", "\n", texto)
    return texto.strip()
