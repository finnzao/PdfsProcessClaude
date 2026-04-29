"""
utils/tipos_pecas.py — Classificação de peças processuais por palavras-chave.

Cada peça extraída do PDF é classificada em um TIPO. O TIPO determina:
  - se a peça é mantida na íntegra (PECAS_COMPLETAS)
  - se vira só uma linha de resumo (PECAS_RESUMO)
  - se é descartada (PECAS_DESCARTE)

Como adicionar novo tipo:
    1. Crie a tupla (NOME, [palavras_chave]) em TIPOS_PECAS
    2. Inclua o NOME em PECAS_COMPLETAS, PECAS_RESUMO ou PECAS_DESCARTE
    3. Mais específicas vêm primeiro (ordem importa em classificar_peca)
"""

#  Lista de tipos com palavras-chave de identificação

# IMPORTANTE: a ordem importa. Tipos mais específicos antes dos genéricos.
# Ex: "TRANSITO_JULGADO" antes de "CERTIDÃO" porque ambos podem aparecer
# no mesmo documento, e o trânsito em julgado é informação mais valiosa.

TIPOS_PECAS = [
    # ── Início do procedimento ──
    ("AUTUAÇÃO", ["autuação", "autuo o(a) presente"]),
    ("PORTARIA", ["portaria", "resolve:", "instaurar inquérito"]),
    ("DENÚNCIA", [
        "oferece a presente den", "ofereço a presente den",
        "denuncia como incurso", "denuncio como incurso",
    ]),

    # ── Decisões de mérito ──
    ("SENTENÇA", [
        "vistos, etc", "julgo procedente", "julgo improcedente",
        "condeno o r", "absolvo o r",
    ]),
    ("PRONÚNCIA", ["pronuncio o r", "pronuncia o r"]),
    ("ALEGAÇÕES", ["alegações finais", "memoriais"]),
    ("RESPOSTA", ["resposta à acusação", "defesa prévia"]),
    ("RECURSO", ["apelação", "razões recursais", "contrarrazões"]),

    # ── Eventos críticos para análise de cautelar (alta prioridade) ──
    ("TRANSITO_JULGADO", [
        "trânsito em julgado", "transitou em julgado", "transitada em julgado",
        "expedir guia de execução", "guia de recolhimento",
    ]),
    ("EXTINCAO_PUNIBILIDADE", [
        "extinta a punibilidade", "extingo a punibilidade",
        "declaro extinta a punibilidade", "art. 107 do código penal",
    ]),
    ("LIBERDADE_PROVISORIA", [
        "concedo liberdade provisória", "concedo a liberdade provisória",
        "defiro a liberdade provisória", "art. 321 do cpp",
    ]),
    ("CAUTELAR_319", [
        "medida cautelar diversa", "medidas cautelares diversas",
        "art. 319 do cpp", "art. 319, i", "comparecimento periódico",
        "comparecer mensalmente", "comparecer quinzenalmente",
        "comparecer bimestralmente", "comparecer em juízo",
    ]),
    ("REVOGACAO_CAUTELAR", [
        "revogo as cautelares", "revogo a medida cautelar",
        "revogo as medidas cautelares", "extintas as cautelares",
        "extingo as cautelares",
    ]),
    ("PREVENTIVA", [
        "decreto a prisão preventiva", "decreto preventiva",
        "converto em prisão preventiva", "prisão preventiva decretada",
    ]),
    ("AUDIENCIA_CUSTODIA", [
        "audiência de custódia", "homologação do flagrante",
        "homologo o flagrante", "auto de prisão em flagrante",
    ]),
    ("TERMO_COMPROMISSO", [
        "termo de compromisso", "compromisso de comparecimento",
        "ciência das cautelares", "ciência das medidas cautelares",
    ]),
    ("SURSIS_PROCESSUAL", [
        "suspensão condicional do processo", "art. 89 da lei 9.099",
        "sursis processual", "período de prova",
    ]),
    ("ANPP", [
        "acordo de não persecução penal", "anpp",
        "art. 28-a do cpp", "art. 28-a, cpp",
    ]),
    ("TRANSACAO_PENAL", [
        "transação penal", "art. 76 da lei 9.099",
        "homologo a transação",
    ]),

    # ── Investigação ──
    ("BO", [
        "boletim de ocorrência", "dados do registro", "relato/histórico",
    ]),
    ("DECLARAÇÃO", [
        "termo de declarações", "às perguntas do(a) delegado",
    ]),
    ("INTERROGATÓRIO", ["termo de qualificação e interrogatório"]),
    ("RELATÓRIO", [
        "relatório final", "dos fatos e circunstâncias apuradas",
    ]),

    # ── Violência doméstica ──
    ("MPU", [
        "pedido de medida protetiva",
        "medida(s) protetiva(s) de urgência",
    ]),
    ("RISCO", ["formulário nacional de avaliação de risco"]),

    # ── Provas/perícias ──
    ("LAUDO", [
        "laudo de exame", "lesões corporais", "exame médico pericial",
    ]),

    # ── Decisões interlocutórias ──
    ("DECISÃO", ["decido que", "defiro o pedido", "indefiro o pedido"]),
    ("DESPACHO", ["despacho", "cite-se", "intime-se", "cumpra-se"]),

    # ── Audiências ──
    ("ATA", ["ata de audiência", "aberta a audiência"]),

    # ── Comunicações ──
    ("OFÍCIO", ["ofício nº", "oficio nº"]),
    ("CARTA PRECATÓRIA", ["carta precatória"]),
    ("BIC", ["boletim de informação criminal"]),
    ("CERTIDÃO", [
        "certifico que", "certidão", "certidão de publicação",
    ]),
    ("INTIMAÇÃO", ["intimação", "fica intimado"]),
    ("MANDADO", ["mandado de"]),
    ("ALVARÁ", ["alvará de soltura"]),
    ("CONCLUSOS", ["autos conclusos"]),
    ("REMESSA", ["remessa", "faço a remessa"]),
    ("RECIBO", ["recibo de entrega"]),
    ("PETIÇÃO", [
        "petição ministerial", "petição", "registrar ciência",
    ]),

    # ── Lixo a descartar ──
    ("ASSINATURA", ["gerado por sinesp"]),
]


#  Categorização — como cada tipo é tratado no markdown final

# Texto integral preservado (peças importantes para análise)
PECAS_COMPLETAS = {
    "AUTUAÇÃO", "PORTARIA", "DENÚNCIA",
    "SENTENÇA", "PRONÚNCIA", "ALEGAÇÕES", "RESPOSTA", "RECURSO",
    "TRANSITO_JULGADO", "EXTINCAO_PUNIBILIDADE",
    "LIBERDADE_PROVISORIA", "CAUTELAR_319", "REVOGACAO_CAUTELAR",
    "PREVENTIVA", "AUDIENCIA_CUSTODIA", "TERMO_COMPROMISSO",
    "SURSIS_PROCESSUAL", "ANPP", "TRANSACAO_PENAL",
    "BO", "DECLARAÇÃO", "INTERROGATÓRIO", "RELATÓRIO",
    "MPU", "RISCO", "LAUDO",
    "DECISÃO", "DESPACHO", "ATA", "CARTA PRECATÓRIA", "PETIÇÃO",
}

# Apenas uma linha de resumo (cabeçalho + primeira linha relevante)
PECAS_RESUMO = {
    "OFÍCIO", "BIC", "CERTIDÃO", "INTIMAÇÃO", "MANDADO",
    "ALVARÁ", "CONCLUSOS", "REMESSA", "RECIBO",
}

# Descartadas completamente
PECAS_DESCARTE = {"ASSINATURA"}


#  Função de classificação

def classificar_peca(texto: str, janela: int = 2000) -> str:
    """
    Identifica o TIPO de uma peça processual por palavras-chave.
    Examina apenas os primeiros `janela` caracteres (cabeçalho/início).

    Retorna o nome do tipo identificado, ou "DOC" se nada bater.

    >>> classificar_peca("OFEREÇO A PRESENTE DENÚNCIA contra...")
    'DENÚNCIA'
    >>> classificar_peca("CONCEDO LIBERDADE PROVISÓRIA ao réu...")
    'LIBERDADE_PROVISORIA'
    """
    texto_lower = texto.lower()[:janela]
    for tipo, palavras_chave in TIPOS_PECAS:
        if any(kw in texto_lower for kw in palavras_chave):
            return tipo
    return "DOC"
