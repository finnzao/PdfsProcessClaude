"""utils/tipos_pecas.py — Mapeamento canonico de tipos de pecas processuais."""

# Lista canonica (rotulos como usados pelo classificador)
TIPO_LISTA_COMPLETA = [
    "DENUNCIA",
    "BOLETIM_OCORRENCIA",
    "AUTO_PRISAO_FLAGRANTE",
    "AUDIENCIA_CUSTODIA",
    "LIBERDADE_PROVISORIA",
    "PREVENTIVA",
    "REVOGACAO_CAUTELAR",
    "CAUTELAR_319",
    "TERMO_COMPROMISSO",
    "SURSIS_PROCESSUAL",
    "ANPP",
    "TRANSACAO_PENAL",
    "CUMPRIMENTO_SURSIS",
    "CUMPRIMENTO_ANPP",
    "SENTENCA",
    "TRANSITO_JULGADO",
    "EXTINCAO_PUNIBILIDADE",
    "MANIFESTACAO_MP",
    "MANIFESTACAO_DEFESA",
    "DESPACHO",
    "DECISAO",
    "ALEGACOES_FINAIS",
    "DOC",
]


# Mapa de aliases/variacoes -> rotulo canonico
TIPO_PECA_PARA_NORMALIZADO = {
    "denuncia": "DENUNCIA",
    "denúncia": "DENUNCIA",
    "petição inicial": "DENUNCIA",

    "bo": "BOLETIM_OCORRENCIA",
    "boletim": "BOLETIM_OCORRENCIA",
    "boletim de ocorrência": "BOLETIM_OCORRENCIA",
    "ocorrencia": "BOLETIM_OCORRENCIA",

    "apf": "AUTO_PRISAO_FLAGRANTE",
    "auto de prisão em flagrante": "AUTO_PRISAO_FLAGRANTE",
    "flagrante": "AUTO_PRISAO_FLAGRANTE",

    "audiencia de custodia": "AUDIENCIA_CUSTODIA",
    "audiência de custódia": "AUDIENCIA_CUSTODIA",
    "custodia": "AUDIENCIA_CUSTODIA",

    "liberdade provisoria": "LIBERDADE_PROVISORIA",
    "liberdade provisória": "LIBERDADE_PROVISORIA",
    "lp": "LIBERDADE_PROVISORIA",

    "prisao preventiva": "PREVENTIVA",
    "prisão preventiva": "PREVENTIVA",
    "preventiva": "PREVENTIVA",

    "revogacao": "REVOGACAO_CAUTELAR",
    "revogação": "REVOGACAO_CAUTELAR",
    "revogacao de cautelar": "REVOGACAO_CAUTELAR",

    "cautelar 319": "CAUTELAR_319",
    "cautelares": "CAUTELAR_319",
    "medidas cautelares": "CAUTELAR_319",

    "termo de compromisso": "TERMO_COMPROMISSO",
    "termo de cautelares": "TERMO_COMPROMISSO",

    "sursis": "SURSIS_PROCESSUAL",
    "sursis processual": "SURSIS_PROCESSUAL",
    "suspensao condicional do processo": "SURSIS_PROCESSUAL",
    "suspensão condicional do processo": "SURSIS_PROCESSUAL",

    "anpp": "ANPP",
    "acordo de nao persecucao penal": "ANPP",
    "acordo de não persecução penal": "ANPP",

    "transacao penal": "TRANSACAO_PENAL",
    "transação penal": "TRANSACAO_PENAL",

    "cumprimento sursis": "CUMPRIMENTO_SURSIS",
    "cumprimento anpp": "CUMPRIMENTO_ANPP",

    "sentenca": "SENTENCA",
    "sentença": "SENTENCA",
    "decisao final": "SENTENCA",

    "transito em julgado": "TRANSITO_JULGADO",
    "trânsito em julgado": "TRANSITO_JULGADO",
    "transito": "TRANSITO_JULGADO",

    "extincao da punibilidade": "EXTINCAO_PUNIBILIDADE",
    "extinção da punibilidade": "EXTINCAO_PUNIBILIDADE",

    "mp": "MANIFESTACAO_MP",
    "manifestacao mp": "MANIFESTACAO_MP",
    "manifestacao do mp": "MANIFESTACAO_MP",
    "promotor": "MANIFESTACAO_MP",
    "promocao": "MANIFESTACAO_MP",

    "manifestacao defesa": "MANIFESTACAO_DEFESA",
    "defesa": "MANIFESTACAO_DEFESA",
    "resposta a acusacao": "MANIFESTACAO_DEFESA",

    "despacho": "DESPACHO",
    "decisao": "DECISAO",
    "decisão": "DECISAO",

    "alegacoes finais": "ALEGACOES_FINAIS",
    "alegações finais": "ALEGACOES_FINAIS",
    "memoriais": "ALEGACOES_FINAIS",

    "doc": "DOC",
    "documento": "DOC",
    "anexo": "DOC",
}


def normalizar_tipo_peca(tipo: str) -> str:
    """Normaliza um nome de peca para o rotulo canonico. Retorna 'DOC' por default."""
    if not tipo:
        return "DOC"
    chave = tipo.strip().lower()
    if chave in TIPO_PECA_PARA_NORMALIZADO:
        return TIPO_PECA_PARA_NORMALIZADO[chave]
    chave_up = tipo.strip().upper()
    if chave_up in TIPO_LISTA_COMPLETA:
        return chave_up
    return "DOC"
