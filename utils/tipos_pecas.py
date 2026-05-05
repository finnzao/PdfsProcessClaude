"""
utils/tipos_pecas.py — Classificação ponderada de peças processuais.

Porta para Python a abordagem do classificador JS (index.html):
  - Cada tipo tem lista de sinais com peso (1=fraco, 3=médio, 6=forte, 10=decisivo)
  - Bônus se o sinal aparece nos primeiros 400 chars (cabeçalho)
  - Score mínimo por tipo para evitar falso positivo em citações
  - Sinais podem ser str (substring) ou re.Pattern

Como adicionar novo tipo:
    1. Adicione tupla (TIPO, [(sinal, peso), ...], min_score) em TIPOS_PECAS
    2. Inclua TIPO em PECAS_COMPLETAS, PECAS_RESUMO ou PECAS_DESCARTE
    3. Sinais mais específicos primeiro
"""

import re
from typing import Pattern, Union

Sinal = Union[str, Pattern]
SinalPeso = tuple[Sinal, int]
DefTipo = tuple[str, list[SinalPeso], int]


# Cada entrada: (TIPO, [(sinal, peso)...], min_score_para_aceitar)

TIPOS_PECAS: list[DefTipo] = [
    ("AUTUAÇÃO", [
        (re.compile(r"\bauto de autua[çc][aã]o\b", re.I), 10),
        (re.compile(r"\bautuo o\(a\) presente\b", re.I), 10),
    ], 6),

    ("PORTARIA", [
        (re.compile(r"^[\s#]*PORTARIA\b", re.I | re.M), 10),
        (re.compile(r"\bportaria n[°º]\s*\d", re.I), 10),
        (re.compile(r"\binstaurar? inqu[ée]rito policial\b", re.I), 8),
        (re.compile(r"\bresolve:\s*$", re.I | re.M), 3),
    ], 8),

    ("DENÚNCIA", [
        (re.compile(r"\boferec[eo]\s+a\s+presente\s+den[úu]ncia\b", re.I), 10),
        (re.compile(r"\bden(?:uncia|úncia)\s+como\s+incurso\b", re.I), 10),
        (re.compile(r"\bminist[ée]rio p[úu]blico.*oferec[eo]\b", re.I), 6),
        # Cabeçalho típico
        (re.compile(r"^[\s#]*DEN[ÚU]NCIA\b", re.I | re.M), 10),
        # "OFEREÇO A PRESENTE DENÚNCIA contra..." — comum no início da peça
        (re.compile(r"\bA\s+PRESENTE\s+DEN[ÚU]NCIA\b", re.I), 8),
        (re.compile(r"\bA(?:O)?S?\s+(?:Ex|MM\.?)?\s*Ju[íi]z[a-zo\s]*da\s+Vara\b[\s\S]{0,500}\bden[úu]ncia\b", re.I), 8),
    ], 8),

    ("SENTENÇA", [
        (re.compile(r"^[\s#]*SENTEN[ÇC]A\b", re.I | re.M), 10),
        (re.compile(r"\bjulgo (?:totalmente )?procedente\b", re.I), 8),
        (re.compile(r"\bjulgo (?:totalmente )?improcedente\b", re.I), 8),
        (re.compile(r"\bcondeno o r[ée]u\b", re.I), 8),
        (re.compile(r"\babsolvo o r[ée]u\b", re.I), 8),
        (re.compile(r"\bjulgo extinto\b.*(?:m[ée]rito|execu)", re.I), 6),
    ], 8),

    ("PRONÚNCIA", [
        (re.compile(r"\bpronuncio o r[ée]u\b", re.I), 10),
        (re.compile(r"\bimpronuncio o r[ée]u\b", re.I), 10),
    ], 8),

    ("ALEGAÇÕES", [
        (re.compile(r"\balega[çc][õo]es finais\b", re.I), 10),
        (re.compile(r"\bmemoriais finais\b", re.I), 8),
    ], 6),

    ("RESPOSTA", [
        (re.compile(r"\bresposta [àa] acusa[çc][aã]o\b", re.I), 10),
        (re.compile(r"\bdefesa pr[ée]via\b", re.I), 8),
    ], 6),

    ("RECURSO", [
        (re.compile(r"^[\s#]*(?:RAZÕES DE )?APELA[ÇC][ÃA]O\s*$", re.I | re.M), 10),
        (re.compile(r"^[\s#]*(?:CONTRA)?RAZÕES RECURSAIS\b", re.I | re.M), 10),
        (re.compile(r"\binterp[õo]e o presente recurso\b", re.I), 10),
        (re.compile(r"\binterp[õo]e a presente apela[çc][aã]o\b", re.I), 10),
        (re.compile(r"\btempestividade do presente recurso\b", re.I), 6),
        # Apelação sozinha tem peso baixo (citações em ementas)
        (re.compile(r"\bapela[çc][aã]o\b", re.I), 1),
    ], 8),

    # ── Eventos críticos para análise de cautelar ──

    ("AUDIENCIA_CUSTODIA", [
        (re.compile(r"\baudi[êe]ncia de cust[óo]dia\b", re.I), 10),
        (re.compile(r"\bart\.?\s*310[\s,]+(?:caput|do cpp|cpp)", re.I), 8),
        (re.compile(r"\bhomologa[çc][aã]o do flagrante\b", re.I), 8),
        (re.compile(r"\bauto de pris[aã]o em flagrante\b", re.I), 6),
    ], 8),

    ("LIBERDADE_PROVISORIA", [
        (re.compile(r"\bconcedo (?:a )?liberdade provis[óo]ria\b", re.I), 10),
        (re.compile(r"\bdefiro (?:a )?liberdade provis[óo]ria\b", re.I), 10),
        (re.compile(r"\bart\.?\s*321\s*(?:do\s*)?cpp", re.I), 8),
    ], 8),

    ("CAUTELAR_319", [
        (re.compile(r"\bart\.?\s*319[\s,]+(?:i|do cpp)", re.I), 10),
        (re.compile(r"\bmedidas? cautelares? diversas?\b", re.I), 8),
        (re.compile(r"\bcomparecimento (?:mensal|bimestral|quinzenal|peri[óo]dico)", re.I), 10),
        (re.compile(r"\bcomparecer (?:mensal|bimestral|quinzenal)mente\b", re.I), 10),
    ], 8),

    ("REVOGACAO_CAUTELAR", [
        (re.compile(r"\brevogo as (?:medidas )?cautelares\b", re.I), 10),
        (re.compile(r"\bextintas as cautelares\b", re.I), 10),
        (re.compile(r"\bextingo as (?:medidas )?cautelares\b", re.I), 10),
    ], 8),

    ("PREVENTIVA", [
        (re.compile(r"\bdecreto (?:a )?pris[aã]o preventiva\b", re.I), 10),
        (re.compile(r"\bconverto em pris[aã]o preventiva\b", re.I), 10),
    ], 8),

    ("TERMO_COMPROMISSO", [
        (re.compile(r"\btermo de compromisso\b", re.I), 10),
        (re.compile(r"\bcompromisso de comparecimento\b", re.I), 10),
        (re.compile(r"\bci[êe]ncia das (?:medidas )?cautelares\b", re.I), 8),
    ], 8),

    ("SURSIS_PROCESSUAL", [
        (re.compile(r"\bsuspens[aã]o condicional do processo\b", re.I), 10),
        (re.compile(r"\bart\.?\s*89\s*(?:da\s*)?lei\s*9[.\s]?099", re.I), 10),
        (re.compile(r"\bsursis processual\b", re.I), 8),
        (re.compile(r"\bper[íi]odo de prova\b", re.I), 6),
    ], 8),

    ("ANPP", [
        (re.compile(r"\bacordo de n[aã]o persecu[çc][aã]o penal\b", re.I), 10),
        (re.compile(r"\bart\.?\s*28[-\s]?a\s*(?:do\s*)?cpp", re.I), 10),
        (re.compile(r"\banpp\b", re.I), 6),
    ], 8),

    ("TRANSACAO_PENAL", [
        (re.compile(r"\btransa[çc][aã]o penal\b", re.I), 10),
        (re.compile(r"\bart\.?\s*76\s*(?:da\s*)?lei\s*9[.\s]?099", re.I), 10),
    ], 8),

    ("EXTINCAO_PUNIBILIDADE", [
        (re.compile(r"\bdeclaro extinta a punibilidade\b", re.I), 10),
        (re.compile(r"\bextin[gç]o a punibilidade\b", re.I), 10),
        (re.compile(r"\bextinta a punibilidade\b", re.I), 8),
        (re.compile(r"\bart\.?\s*107\s*(?:do\s*)?cp\b", re.I), 6),
    ], 8),

    # Cumprimento que extingue (PROVA, não homologação)
    # Pesos altos para vencer o sinal genérico de EXTINCAO_PUNIBILIDADE
    # quando ambos aparecem (caso típico: sentença extingue por cumprimento)
    ("CUMPRIMENTO_SURSIS", [
        (re.compile(r"\bcumprido o per[íi]odo de prova\b", re.I), 20),
        (re.compile(r"\bart\.?\s*89[\s,]+§\s*5", re.I), 20),
    ], 15),

    ("CUMPRIMENTO_ANPP", [
        (re.compile(r"\bcumpridas as condi[çc][õo]es\b.*\banpp\b", re.I), 20),
        (re.compile(r"\bart\.?\s*28[-\s]?a[\s,]+§\s*13", re.I), 20),
    ], 15),

    ("TRANSITO_JULGADO", [
        (re.compile(r"\btr[âa]nsito em julgado\b", re.I), 10),
        (re.compile(r"\btransitou em julgado\b", re.I), 10),
        (re.compile(r"\btransitada em julgado\b", re.I), 10),
        (re.compile(r"\bexpedir guia de execu[çc][aã]o\b", re.I), 8),
    ], 8),

    # ── Investigação ──
    ("BO", [
        (re.compile(r"\bboletim de ocorr[êe]ncia\b", re.I), 10),
        (re.compile(r"\brelato\/hist[óo]rico\b", re.I), 6),
        (re.compile(r"\bdados do registro\b", re.I), 3),
    ], 8),

    ("DECLARAÇÃO", [
        (re.compile(r"\btermo de declara[çc][õo]es\b", re.I), 10),
        (re.compile(r"\b[àa]s perguntas do\(a\) delegado\b", re.I), 8),
    ], 8),

    ("INTERROGATÓRIO", [
        (re.compile(r"\btermo de (?:qualifica[çc][aã]o e )?interrogat[óo]rio\b", re.I), 10),
    ], 8),

    ("RELATÓRIO", [
        (re.compile(r"\brelat[óo]rio final\b", re.I), 10),
        (re.compile(r"\bdos fatos e circunst[âa]ncias apuradas\b", re.I), 8),
    ], 8),

    ("MPU", [
        (re.compile(r"\bmedida\(?s?\)? protetiva\(?s?\)? de urg[êe]ncia\b", re.I), 10),
        (re.compile(r"\bpedido de medida protetiva\b", re.I), 10),
    ], 8),

    ("RISCO", [
        (re.compile(r"\bformul[áa]rio nacional de avalia[çc][aã]o de risco\b", re.I), 10),
    ], 8),

    ("LAUDO", [
        (re.compile(r"\blaudo de exame\b", re.I), 10),
        (re.compile(r"\bexame m[ée]dico pericial\b", re.I), 10),
    ], 8),

    ("DECISÃO", [
        (re.compile(r"^[\s#]*DECIS[ÃA]O\b", re.I | re.M), 10),
        (re.compile(r"\bdecido que\b", re.I), 8),
        (re.compile(r"\b(?:de|in)firo o pedido\b", re.I), 8),
    ], 8),

    ("DESPACHO", [
        (re.compile(r"^[\s#]*DESPACHO\b", re.I | re.M), 10),
        (re.compile(r"\bvistos,?\s*etc\.?\b", re.I), 6),
        (re.compile(r"\bcite-se\b", re.I), 4),
        (re.compile(r"\bintime-se\b", re.I), 3),
        (re.compile(r"\bcumpra-se\b", re.I), 3),
    ], 8),

    ("ATA", [
        (re.compile(r"\bata de audi[êe]ncia\b", re.I), 10),
        (re.compile(r"\baberta a audi[êe]ncia\b", re.I), 8),
    ], 8),

    ("OFÍCIO", [
        (re.compile(r"^[\s#]*OF[ÍI]CIO\s+n[°º]", re.I | re.M), 10),
        (re.compile(r"\bof[íi]cio n[°º]\s*[\d.\-/]+", re.I), 8),
    ], 6),

    ("CARTA PRECATÓRIA", [
        (re.compile(r"\bcarta precat[óo]ria\b", re.I), 10),
    ], 8),

    ("CERTIDÃO", [
        (re.compile(r"^[\s#]*CERTID[ÃA]O(?:\s+DE\s+\w+)?\s*$", re.I | re.M), 10),
        (re.compile(r"\bcertifico,?\s+para os devidos fins\b", re.I), 8),
        (re.compile(r"\bcertifico que\b", re.I), 6),
    ], 6),

    ("INTIMAÇÃO", [
        (re.compile(r"^[\s#]*INTIMA[ÇC][ÃA]O\b", re.I | re.M), 8),
        (re.compile(r"\bfica(?:m)? (?:a parte |as partes )?intimad[oa]s?\b", re.I), 6),
    ], 6),

    ("MANDADO", [
        (re.compile(r"^[\s#]*MANDADO\s+DE\b", re.I | re.M), 10),
        (re.compile(r"\bmandado de (?:cita|intima|penhora|bus|pris|condu)", re.I), 8),
    ], 8),

    ("ALVARÁ", [
        (re.compile(r"\balvar[áa] de soltura\b", re.I), 10),
    ], 8),

    ("CONCLUSOS", [
        (re.compile(r"\btorno os autos conclusos\b", re.I), 10),
        (re.compile(r"\bautos conclusos\b", re.I), 8),
    ], 8),

    ("REMESSA", [
        (re.compile(r"\bfa[çc]o a remessa\b", re.I), 10),
        (re.compile(r"\btermo de remessa\b", re.I), 10),
    ], 8),

    ("PETIÇÃO", [
        (re.compile(r"^[\s#]*PETI[ÇC][ÃA]O INICIAL\b", re.I | re.M), 10),
        (re.compile(r"\bao?s? ju[íi]zo\s+da?\s+vara\b", re.I), 6),
        (re.compile(r"\bexcelent[íi]ssim[oa]\s+senhor[a]?\s+(?:doutor|dr\.?|ju[íi]z)", re.I), 6),
        (re.compile(r"\bnestes\s+termos,?\s*pede\s+deferimento\b", re.I), 6),
        (re.compile(r"\bpeti[çc][ãa]o ministerial\b", re.I), 8),
    ], 6),

    ("ASSINATURA", [
        (re.compile(r"\bgerado por sinesp\b", re.I), 10),
    ], 10),
]


# ── Categorização para tratamento no markdown final ──────────────

PECAS_COMPLETAS: set[str] = {
    "AUTUAÇÃO", "PORTARIA", "DENÚNCIA", "SENTENÇA", "PRONÚNCIA",
    "ALEGAÇÕES", "RESPOSTA", "RECURSO",
    "AUDIENCIA_CUSTODIA", "LIBERDADE_PROVISORIA", "CAUTELAR_319",
    "REVOGACAO_CAUTELAR", "PREVENTIVA", "TERMO_COMPROMISSO",
    "SURSIS_PROCESSUAL", "ANPP", "TRANSACAO_PENAL",
    "EXTINCAO_PUNIBILIDADE", "CUMPRIMENTO_SURSIS", "CUMPRIMENTO_ANPP",
    "TRANSITO_JULGADO",
    "BO", "DECLARAÇÃO", "INTERROGATÓRIO", "RELATÓRIO",
    "MPU", "RISCO", "LAUDO",
    "DECISÃO", "DESPACHO", "ATA", "CARTA PRECATÓRIA", "PETIÇÃO",
}

PECAS_RESUMO: set[str] = {
    "OFÍCIO", "CERTIDÃO", "INTIMAÇÃO", "MANDADO",
    "ALVARÁ", "CONCLUSOS", "REMESSA",
}

PECAS_DESCARTE: set[str] = {"ASSINATURA"}

# Peças onde a cautelar pode ser fixada (busca direcionada)
PECAS_FONTE_CAUTELAR: set[str] = {
    "AUDIENCIA_CUSTODIA", "LIBERDADE_PROVISORIA", "CAUTELAR_319",
    "ATA", "DECISÃO", "TERMO_COMPROMISSO",
    "SURSIS_PROCESSUAL", "ANPP", "TRANSACAO_PENAL",
}


# ── Função de classificação ──────────────────────────────────────

def _testar_sinal(sinal: Sinal, texto: str, texto_lower: str) -> bool:
    """Testa um sinal (str ou Pattern) contra o texto."""
    if isinstance(sinal, re.Pattern):
        return bool(sinal.search(texto))
    return sinal.lower() in texto_lower


def classificar_peca(texto: str, janela: int = 3000) -> tuple[str, int]:
    """
    Classifica uma peça por scoring ponderado.

    Retorna (tipo, score). Score é diagnóstico — 0 quando nenhum tipo bateu
    o mínimo, valor positivo quando um tipo venceu.

    >>> classificar_peca("OFEREÇO A PRESENTE DENÚNCIA contra...")[0]
    'DENÚNCIA'
    """
    texto_amostra = texto[:janela]
    texto_lower = texto_amostra.lower()
    inicio = texto_amostra[:400]

    melhor_tipo = "DOC"
    melhor_score = 0

    for tipo, sinais, minimo in TIPOS_PECAS:
        score = 0
        for sinal, peso in sinais:
            if _testar_sinal(sinal, texto_amostra, texto_lower):
                score += peso
                # Bônus por aparecer no cabeçalho
                if isinstance(sinal, re.Pattern):
                    if sinal.search(inicio):
                        score += peso
                else:
                    if sinal.lower() in inicio.lower():
                        score += peso

        if score >= minimo and score > melhor_score:
            melhor_tipo = tipo
            melhor_score = score

    return melhor_tipo, melhor_score
