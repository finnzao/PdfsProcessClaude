#!/usr/bin/env python3
"""
scoring.py — Sistema de priorização: impacto × facilidade.

Ordem de prioridade (conforme definido pela vara):
  1. Prescrição (perda irreversível)
  2. Taxa de congestionamento (resolver estoque antigo)
  3. Réu preso (custódia com risco)
  4. Outras metas

Score composto: prioridade = impacto_meta × facilidade_ato
Quanto MAIOR o score, PRIMEIRO na fila de trabalho.
"""


# ── Classificação do executor do próximo ato ──────────────────────

EXECUTOR_CARTORIO = "Cartório"
EXECUTOR_ASSESSORIA = "Assessoria"
EXECUTOR_JUIZ = "Juiz"
EXECUTOR_EXTERNO = "Externo"
EXECUTOR_VERIFICAR = "Verificar"

# Atos e quem executa (mapeamento por palavras-chave no próximo ato)
ATOS_EXECUTOR = {
    EXECUTOR_CARTORIO: [
        "expedir citação", "citar", "intimar", "certificar",
        "juntar", "remeter ao tj", "remessa", "expedir mandado",
        "expedir alvará", "expedir ofício", "publicar",
        "abrir vista ao mp", "reintimar mp", "intimar delegado",
        "contrarrazões", "processar apelação", "processar recurso",
    ],
    EXECUTOR_ASSESSORIA: [
        "minutar sentença", "minutar decisão", "analisar recebimento",
        "analisar absolvição sumária", "pronunciar", "impronunciar",
        "reconhecer prescrição", "minutar", "elaborar",
        "homologar anpp", "homologar transação", "homologar arquivamento",
        "revisar prisão preventiva", "analisar progressão",
    ],
    EXECUTOR_JUIZ: [
        "assinar", "despachar", "decidir", "sentenciar",
    ],
    EXECUTOR_EXTERNO: [
        "aguardar mp", "aguardar delegado", "aguardar laudo",
        "aguardar arf", "aguardar carta precatória",
        "aguardar contrarrazões", "aguardar resposta",
    ],
}


def classificar_executor(proximo_ato: str) -> str:
    """Classifica quem deve executar o próximo ato."""
    ato_lower = proximo_ato.lower().strip()
    for executor, keywords in ATOS_EXECUTOR.items():
        for kw in keywords:
            if kw in ato_lower:
                return executor
    return EXECUTOR_VERIFICAR


# ── Facilidade do ato (quanto mais fácil, mais rápido resolve) ────

# Score de 1 a 5: 5 = ato trivial, 1 = ato complexo
FACILIDADE_ATOS = {
    # Nível 5 — Cartório resolve sozinho em minutos
    "expedir citação": 5, "citar": 5, "intimar": 5, "certificar": 5,
    "juntar": 5, "publicar": 5, "abrir vista": 5, "reintimar": 5,
    "expedir mandado": 5, "expedir alvará": 5, "expedir ofício": 5,

    # Nível 4 — Despacho padrão, copiar modelo
    "reconhecer prescrição": 4, "homologar arquivamento": 4,
    "homologar transação": 4, "homologar anpp": 4,
    "remeter ao tj": 4, "processar apelação": 4, "processar recurso": 4,
    "nomear defensor": 4, "suspender processo": 4,
    "designar audiência": 4, "redesignar": 4,

    # Nível 3 — Decisão com análise leve
    "receber denúncia": 3, "analisar recebimento": 3,
    "deferir medida protetiva": 3, "revisar prisão": 3,
    "revogar sursis": 3, "intimar delegado": 3,

    # Nível 2 — Decisão com análise jurídica
    "pronunciar": 2, "impronunciar": 2,
    "absolvição sumária": 2, "analisar absolvição": 2,
    "decretar preventiva": 2, "liberdade provisória": 2,

    # Nível 1 — Trabalho pesado
    "minutar sentença": 1, "sentenciar": 1,
    "minutar decisão": 1,
}


def calcular_facilidade(proximo_ato: str) -> int:
    """Retorna score de facilidade de 1 a 5."""
    ato_lower = proximo_ato.lower().strip()
    for kw, score in FACILIDADE_ATOS.items():
        if kw in ato_lower:
            return score
    return 3  # default: médio


# ── Impacto na meta ──────────────────────────────────────────────

def calcular_impacto_meta(
    risco_prescricao: str,
    dias_parado: int,
    reu_preso: bool = False,
    urgencia_crime: str = "MEDIA",
) -> tuple:
    """
    Calcula score de impacto na meta.
    Retorna (score_impacto, meta_principal).

    Pesos:
      Prescrição:         base 10000
      Congestionamento:   base 1000-5000 (por dias)
      Réu preso:          base 3000
      Outras:             base 100-500
    """
    score = 0
    meta = "Outras"

    # 1. PRESCRIÇÃO — prioridade máxima
    peso_prescricao = {
        "PRESCRITO": 15000,
        "IMINENTE": 12000,
        "ATENCAO": 10000,
        "BAIXO": 500,
        "SEM RISCO": 0,
    }
    score_presc = peso_prescricao.get(risco_prescricao, 0)
    if score_presc >= 10000:
        meta = "Prescrição"

    # 2. CONGESTIONAMENTO — por dias parado
    if dias_parado >= 1825:       # 5+ anos
        score_congest = 5000
    elif dias_parado >= 1095:     # 3+ anos
        score_congest = 4000
    elif dias_parado >= 730:      # 2+ anos
        score_congest = 3000
    elif dias_parado >= 365:      # 1+ ano
        score_congest = 2000
    elif dias_parado >= 180:
        score_congest = 1000
    else:
        score_congest = 500

    if meta == "Outras" and dias_parado >= 365:
        meta = "Congestionamento"

    # 3. RÉU PRESO
    score_preso = 3000 if reu_preso else 0
    if reu_preso and meta == "Outras":
        meta = "Réu preso"

    # 4. URGÊNCIA DO CRIME (gravidade)
    peso_crime = {
        "CRITICA": 800,
        "ALTA": 400,
        "MEDIA": 200,
        "BAIXA": 100,
    }
    score_crime = peso_crime.get(urgencia_crime, 200)

    score = score_presc + score_congest + score_preso + score_crime
    return score, meta


# ── Score composto final ─────────────────────────────────────────

def calcular_prioridade(
    risco_prescricao: str,
    dias_parado: int,
    proximo_ato: str,
    reu_preso: bool = False,
    urgencia_crime: str = "MEDIA",
) -> dict:
    """
    Calcula prioridade final: impacto × facilidade.

    Retorna dict com todos os campos de priorização.
    """
    impacto, meta = calcular_impacto_meta(
        risco_prescricao, dias_parado, reu_preso, urgencia_crime
    )
    facilidade = calcular_facilidade(proximo_ato)
    executor = classificar_executor(proximo_ato)

    # Score composto: impacto × facilidade
    # Facilidade multiplica por 1.0 a 2.0 (não queremos que anule impacto)
    multiplicador = 1.0 + (facilidade - 1) * 0.25  # 1=1.0, 2=1.25, 3=1.5, 4=1.75, 5=2.0
    score_final = int(impacto * multiplicador)

    return {
        "score_prioridade": score_final,
        "score_impacto": impacto,
        "facilidade_ato": facilidade,
        "meta_principal": meta,
        "executor": executor,
    }


# ── Nível de prioridade (para a planilha) ────────────────────────

def nivel_prioridade(score: int) -> str:
    """Converte score em nível legível."""
    if score >= 15000:
        return "URGENTÍSSIMA"
    if score >= 10000:
        return "URGENTE"
    if score >= 5000:
        return "ALTA"
    if score >= 2000:
        return "MÉDIA"
    return "NORMAL"
