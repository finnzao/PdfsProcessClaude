"""
utils/sinalizadores.py — Detecção proativa de dados estruturados em peças.

Enquanto extrair_processos.py CLASSIFICA peças por tipo, este módulo CAPTURA
dados específicos (CPFs, telefones, datas, sinais de cautelar, etc.) que
ajudam a montar o cabeçalho "DADOS DETECTADOS" no markdown final.

Uso típico:
    from utils.sinalizadores import detectar_dados_pessoais, detectar_eventos_cautelares

    dados = detectar_dados_pessoais(texto_completo)
    eventos = detectar_eventos_cautelares(grupos_de_pecas)
"""

import re

#  Regex de extração de dados pessoais

RE_CPF = re.compile(r'\b(\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b')
RE_RG = re.compile(
    r'\b(?:RG|R\.G\.|identidade)[:.\s]+'
    r'([\d.\-]+(?:\s*[/-]?\s*[A-Z]{2,5})?)',
    re.IGNORECASE,
)
RE_TELEFONE = re.compile(
    r'\(?\b(\d{2})\)?\s*((?:9\s*\d{4})|(?:\d{4,5}))\s*[-.\s]?\s*(\d{4})\b'
)
RE_CEP = re.compile(r'\b(\d{5}-?\d{3})\b')

# Datas no formato dd/mm/aaaa ou dd-mm-aaaa
RE_DATA = re.compile(r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b')

# Datas por extenso: "15 de março de 2024"
RE_DATA_EXTENSO = re.compile(
    r'\b(\d{1,2})\s+de\s+'
    r'(janeiro|fevereiro|março|abril|maio|junho|'
    r'julho|agosto|setembro|outubro|novembro|dezembro)'
    r'\s+de\s+(\d{4})\b',
    re.IGNORECASE,
)


#  Palavras-chave para detecção de eventos cautelares

PALAVRAS_CAUTELAR = [
    "art. 319", "art 319", "comparecimento periódico",
    "comparecer mensalmente", "comparecer quinzenalmente",
    "comparecer bimestralmente", "comparecer em juízo",
    "medida cautelar", "medidas cautelares",
    "liberdade provisória", "art. 321",
]

PALAVRAS_REVOGACAO = [
    "revogo as cautelares", "revogo a medida",
    "revogo as medidas cautelares", "extintas as cautelares",
    "extingo as cautelares",
]

PALAVRAS_EXTINCAO = [
    "extinta a punibilidade", "extingo a punibilidade",
    "declaro extinta a punibilidade", "art. 107",
    "prescrição reconhecida", "prescrita a pretensão",
]

PALAVRAS_TRANSITO = [
    "trânsito em julgado", "transitou em julgado",
    "transitada em julgado", "expedir guia de execução",
]

PALAVRAS_PRESO = [
    "decreto a prisão preventiva", "decreto preventiva",
    "expedir mandado de prisão", "preso preventivamente",
    "recolhido ao", "custodiado em",
]


#  Marcadores para diferenciar papéis processuais
# Critical: nunca capturar CPF da vítima como sendo do réu.

PALAVRAS_REU = [
    "réu:", "réu(é):", "acusado:", "indiciado:", "denunciado:",
    "investigado:", "qualificação do(a) acusado",
    "qualificação do indiciado", "qualificação do réu",
]

PALAVRAS_VITIMA = [
    "vítima:", "ofendido:", "ofendida:",
    "qualificação da vítima", "dados da vítima",
]

PALAVRAS_TESTEMUNHA = [
    "testemunha:", "testemunhas:", "qualificação da testemunha",
]


#  Funções de detecção

def _coletar_unicos(matches, max_itens: int = 10) -> list:
    """Remove duplicatas mantendo ordem; limita ao máximo."""
    vistos = set()
    result = []
    for m in matches:
        chave = m if isinstance(m, str) else str(m)
        if chave not in vistos:
            vistos.add(chave)
            result.append(m)
            if len(result) >= max_itens:
                break
    return result


def detectar_dados_pessoais(texto: str) -> dict:
    """
    Faz uma varredura no texto extraindo CPFs, telefones, RGs, CEPs e datas.

    Retorna dict com listas (sempre limitadas a 10 itens cada).

    NÃO diferencia ainda papel processual (réu/vítima) — apenas detecta
    presença. A diferenciação fica para o Claude no momento da análise.
    """
    cpfs = _coletar_unicos(RE_CPF.findall(texto))
    rgs = _coletar_unicos(RE_RG.findall(texto), max_itens=5)
    ceps = _coletar_unicos(RE_CEP.findall(texto), max_itens=5)

    # Telefones: a regex retorna tuplas (DDD, parte_meio, parte_final)
    tels_brutos = RE_TELEFONE.findall(texto)
    tels_formatados = []
    for ddd, meio, fim in tels_brutos:
        # Filtra falsos positivos óbvios
        if ddd in ('19', '20'):  # provavelmente "19/12" ou "2024"
            continue
        meio_limpo = meio.replace(' ', '')
        tels_formatados.append(f"({ddd}) {meio_limpo}-{fim}")
    tels_unicos = _coletar_unicos(tels_formatados, max_itens=5)

    datas = _coletar_unicos(
        [f"{d}/{m}/{a}" for d, m, a in RE_DATA.findall(texto)],
        max_itens=15,
    )

    return {
        "cpfs": cpfs,
        "rgs": rgs,
        "telefones": tels_unicos,
        "ceps": ceps,
        "datas": datas,
    }


def detectar_eventos_cautelares(grupos: list) -> dict:
    """
    Recebe a lista de grupos de peças (output do extrator) e identifica
    eventos importantes para análise da cautelar.

    Cada grupo tem: tipo, pag_ini, pag_fim, texto, doc_ids.

    Retorna um índice estruturado para o Claude consultar antes de mergulhar
    no texto completo.
    """
    indice = {
        "tem_audiencia_custodia": False,
        "tem_liberdade_provisoria": False,
        "tem_cautelar_319": False,
        "tem_termo_compromisso": False,
        "tem_sursis_processual": False,
        "tem_anpp": False,
        "tem_transacao_penal": False,
        "tem_revogacao": False,
        "tem_preventiva_decretada": False,
        "tem_sentenca": False,
        "tem_transito_julgado": False,
        "tem_extincao_punibilidade": False,
        "eventos": [],
    }

    tipos_cautelares = {
        "AUDIENCIA_CUSTODIA": "tem_audiencia_custodia",
        "LIBERDADE_PROVISORIA": "tem_liberdade_provisoria",
        "CAUTELAR_319": "tem_cautelar_319",
        "TERMO_COMPROMISSO": "tem_termo_compromisso",
        "SURSIS_PROCESSUAL": "tem_sursis_processual",
        "ANPP": "tem_anpp",
        "TRANSACAO_PENAL": "tem_transacao_penal",
        "REVOGACAO_CAUTELAR": "tem_revogacao",
        "PREVENTIVA": "tem_preventiva_decretada",
        "SENTENÇA": "tem_sentenca",
        "TRANSITO_JULGADO": "tem_transito_julgado",
        "EXTINCAO_PUNIBILIDADE": "tem_extincao_punibilidade",
    }

    for grupo in grupos:
        tipo = grupo.get("tipo", "")
        if tipo in tipos_cautelares:
            indice[tipos_cautelares[tipo]] = True
            # Captura primeira data encontrada na peça
            datas = RE_DATA.findall(grupo.get("texto", "")[:5000])
            primeira_data = (
                f"{datas[0][0]}/{datas[0][1]}/{datas[0][2]}" if datas else None
            )
            indice["eventos"].append({
                "tipo": tipo,
                "pagina": (
                    f"{grupo['pag_ini']}-{grupo['pag_fim']}"
                    if grupo['pag_ini'] != grupo['pag_fim']
                    else f"{grupo['pag_ini']}"
                ),
                "doc_ids": grupo.get("doc_ids", []),
                "data_detectada": primeira_data,
                "trecho": _primeira_frase_significativa(grupo.get("texto", "")),
            })

    return indice


def _primeira_frase_significativa(texto: str, max_chars: int = 200) -> str:
    """Pega a primeira linha não-vazia significativa para preview."""
    for linha in texto.split('\n'):
        linha_limpa = linha.strip().strip('#').strip('*').strip()
        if len(linha_limpa) >= 20:
            return linha_limpa[:max_chars]
    return texto[:max_chars].strip()


def detectar_sinalizadores_processuais(grupos: list) -> dict:
    """
    Sumário de alto nível usado no cabeçalho do markdown.
    Permite ao Claude descartar rapidamente processos sem cautelar.
    """
    eventos = detectar_eventos_cautelares(grupos)

    # Inferir fase aparente
    if eventos["tem_transito_julgado"]:
        fase = "Sentenciado com trânsito em julgado"
    elif eventos["tem_extincao_punibilidade"]:
        fase = "Punibilidade extinta"
    elif eventos["tem_sentenca"]:
        fase = "Sentenciado, recurso/trânsito pendente"
    elif eventos["tem_revogacao"]:
        fase = "Cautelares revogadas"
    elif eventos["tem_preventiva_decretada"]:
        fase = "Réu preso preventivamente"
    elif eventos["tem_cautelar_319"] or eventos["tem_liberdade_provisoria"]:
        fase = "Em liberdade com cautelar ativa"
    elif eventos["tem_audiencia_custodia"]:
        fase = "Pós-flagrante (custódia realizada)"
    else:
        fase = "Sem eventos de cautelar identificados"

    # Inferir provável status da cautelar de comparecimento
    if eventos["tem_extincao_punibilidade"] or eventos["tem_transito_julgado"]:
        prob_cautelar = "EXTINTA (cessou com sentença/extinção)"
    elif eventos["tem_revogacao"]:
        prob_cautelar = "REVOGADA"
    elif eventos["tem_preventiva_decretada"]:
        prob_cautelar = "CONVERTIDA EM PREVENTIVA"
    elif eventos["tem_cautelar_319"] or eventos["tem_liberdade_provisoria"]:
        prob_cautelar = "PROVAVELMENTE ATIVA"
    elif eventos["tem_sursis_processual"] or eventos["tem_anpp"]:
        prob_cautelar = "VERIFICAR (sursis/ANPP — pode ter cumprido)"
    else:
        prob_cautelar = "SEM CAUTELAR DETECTADA"

    return {
        "fase_aparente": fase,
        "provavel_status_cautelar": prob_cautelar,
        "eventos": eventos,
    }
