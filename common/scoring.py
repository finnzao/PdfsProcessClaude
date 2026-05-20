#!/usr/bin/env python3
"""scoring.py — Sistema de priorização: impacto × facilidade."""

EXECUTOR_CARTORIO = "Cartório"
EXECUTOR_ASSESSORIA = "Assessoria"
EXECUTOR_JUIZ = "Juiz"
EXECUTOR_EXTERNO = "Externo"
EXECUTOR_VERIFICAR = "Verificar"

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
    ato_lower = proximo_ato.lower().strip()
    for executor, keywords in ATOS_EXECUTOR.items():
        for kw in keywords:
            if kw in ato_lower:
                return executor
    return EXECUTOR_VERIFICAR


FACILIDADE_ATOS = {
    "expedir citação": 5, "citar": 5, "intimar": 5, "certificar": 5,
    "juntar": 5, "publicar": 5, "abrir vista": 5, "reintimar": 5,
    "expedir mandado": 5, "expedir alvará": 5, "expedir ofício": 5,

    "reconhecer prescrição": 4, "homologar arquivamento": 4,
    "homologar transação": 4, "homologar anpp": 4,
    "remeter ao tj": 4, "processar apelação": 4, "processar recurso": 4,
    "nomear defensor": 4, "suspender processo": 4,
    "designar audiência": 4, "redesignar": 4,

    "receber denúncia": 3, "analisar recebimento": 3,
    "deferir medida protetiva": 3, "revisar prisão": 3,
    "revogar sursis": 3, "intimar delegado": 3,

    "pronunciar": 2, "impronunciar": 2,
    "absolvição sumária": 2, "analisar absolvição": 2,
    "decretar preventiva": 2, "liberdade provisória": 2,

    "minutar sentença": 1, "sentenciar": 1,
    "minutar decisão": 1,
}


def calcular_facilidade(proximo_ato: str) -> int:
    ato_lower = proximo_ato.lower().strip()
    for kw, score in FACILIDADE_ATOS.items():
        if kw in ato_lower:
            return score
    return 3


def calcular_impacto_meta(risco_prescricao, dias_parado, reu_preso=False, urgencia_crime="MEDIA"):
    score = 0
    meta = "Outras"

    peso_prescricao = {
        "PRESCRITO": 15000, "IMINENTE": 12000, "ATENCAO": 10000,
        "BAIXO": 500, "SEM RISCO": 0,
    }
    score_presc = peso_prescricao.get(risco_prescricao, 0)
    if score_presc >= 10000:
        meta = "Prescrição"

    if dias_parado >= 1825:
        score_congest = 5000
    elif dias_parado >= 1095:
        score_congest = 4000
    elif dias_parado >= 730:
        score_congest = 3000
    elif dias_parado >= 365:
        score_congest = 2000
    elif dias_parado >= 180:
        score_congest = 1000
    else:
        score_congest = 500

    if meta == "Outras" and dias_parado >= 365:
        meta = "Congestionamento"

    score_preso = 3000 if reu_preso else 0
    if reu_preso and meta == "Outras":
        meta = "Réu preso"

    peso_crime = {"CRITICA": 800, "ALTA": 400, "MEDIA": 200, "BAIXA": 100}
    score_crime = peso_crime.get(urgencia_crime, 200)

    score = score_presc + score_congest + score_preso + score_crime
    return score, meta


def calcular_prioridade(risco_prescricao, dias_parado, proximo_ato, reu_preso=False, urgencia_crime="MEDIA"):
    impacto, meta = calcular_impacto_meta(risco_prescricao, dias_parado, reu_preso, urgencia_crime)
    facilidade = calcular_facilidade(proximo_ato)
    executor = classificar_executor(proximo_ato)
    multiplicador = 1.0 + (facilidade - 1) * 0.25
    score_final = int(impacto * multiplicador)
    return {
        "score_prioridade": score_final,
        "score_impacto": impacto,
        "facilidade_ato": facilidade,
        "meta_principal": meta,
        "executor": executor,
    }


def nivel_prioridade(score: int) -> str:
    if score >= 15000:
        return "URGENTÍSSIMA"
    if score >= 10000:
        return "URGENTE"
    if score >= 5000:
        return "ALTA"
    if score >= 2000:
        return "MÉDIA"
    return "NORMAL"
