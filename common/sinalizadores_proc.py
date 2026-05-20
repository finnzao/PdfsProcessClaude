"""
common/sinalizadores_proc.py — Deteccao proativa de dados estruturados.

Captura dados especificos (CPFs, telefones, datas, sinais de cautelar)
que ajudam a montar o cabecalho do markdown final.

Verbos decisorios (Decido/Defiro/Indefiro/Concedo/Revogo) tem prioridade
sobre cabecalhos formais ou preambulos genericos.
"""

import re

# ========================================================
#   Regex de extracao de dados pessoais
# ========================================================

RE_CPF = re.compile(r"\b(\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b")
RE_RG = re.compile(
    r"\b(?:RG|R\.G\.|identidade)[:.\s]+([\d.\-]+(?:\s*[/-]?\s*[A-Z]{2,5})?)",
    re.IGNORECASE,
)
RE_TELEFONE = re.compile(
    r"\(?\b(\d{2})\)?\s*((?:9\s*\d{4})|(?:\d{4,5}))\s*[-.\s]?\s*(\d{4})\b"
)
RE_CEP = re.compile(r"\b(\d{5}-?\d{3})\b")
RE_DATA = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b")

# Frases com verbos decisorios — sinal forte de evento processual
RE_VERBOS_DECISORIOS = re.compile(
    r"\b(?:Decido|Defiro|Indefiro|Concedo|Revogo|Homologo|Decreto|Declaro|Absolvo|Condeno)\b",
    re.I,
)

# Cabecalhos/preambulos a ignorar para inferencia de evento
RE_PREAMBULO_RUIDO = re.compile(
    r"^(?:VISTOS|RELATORIO|RELATÓRIO|EMENTA|ACÓRDÃO|ACORDAO)\b",
    re.I | re.M,
)


# ========================================================
#   Helpers
# ========================================================

def _coletar_unicos(matches, max_itens=10):
    vistos = set()
    out = []
    for m in matches:
        chave = m if isinstance(m, str) else str(m)
        if chave not in vistos:
            vistos.add(chave)
            out.append(m)
            if len(out) >= max_itens:
                break
    return out


def detectar_dados_pessoais(texto: str) -> dict:
    cpfs = _coletar_unicos(RE_CPF.findall(texto))
    rgs = _coletar_unicos(RE_RG.findall(texto), max_itens=5)
    ceps = _coletar_unicos(RE_CEP.findall(texto), max_itens=5)

    tels_brutos = RE_TELEFONE.findall(texto)
    tels_formatados = []
    for ddd, meio, fim in tels_brutos:
        if ddd in ("19", "20"):
            continue
        meio_limpo = meio.replace(" ", "")
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


# ========================================================
#   Eventos cautelares
# ========================================================

TIPOS_CAUTELARES = {
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
    "CUMPRIMENTO_SURSIS": "tem_cumprimento_sursis",
    "CUMPRIMENTO_ANPP": "tem_cumprimento_anpp",
}


def _trecho_decisorio(texto: str, max_chars: int = 200) -> str:
    """
    Procura primeira frase com verbo decisorio. Se nao houver,
    cai para a primeira linha significativa ignorando preambulos.
    """
    # Procura linha com verbo decisorio
    for linha in texto.split("\n"):
        l = linha.strip().strip("#").strip("*").strip()
        if len(l) < 15:
            continue
        if RE_VERBOS_DECISORIOS.search(l):
            return l[:max_chars]

    # Fallback: primeira linha significativa, pulando preambulos
    for linha in texto.split("\n"):
        l = linha.strip().strip("#").strip("*").strip()
        if len(l) < 20:
            continue
        if RE_PREAMBULO_RUIDO.match(l):
            continue
        return l[:max_chars]

    return texto[:max_chars].strip()


def detectar_eventos_cautelares(grupos: list) -> dict:
    indice = {v: False for v in TIPOS_CAUTELARES.values()}
    indice["eventos"] = []

    for g in grupos:
        tipo = g.get("tipo", "")
        if tipo in TIPOS_CAUTELARES:
            indice[TIPOS_CAUTELARES[tipo]] = True

            texto = g.get("texto", "")
            datas = RE_DATA.findall(texto[:5000])
            primeira_data = (
                f"{datas[0][0]}/{datas[0][1]}/{datas[0][2]}" if datas else None
            )
            indice["eventos"].append({
                "tipo": tipo,
                "pagina": (
                    f"{g['pag_ini']}-{g['pag_fim']}"
                    if g['pag_ini'] != g['pag_fim']
                    else f"{g['pag_ini']}"
                ),
                "doc_ids": g.get("doc_ids", []),
                "data_detectada": primeira_data,
                "trecho": _trecho_decisorio(texto),
            })

    return indice


def detectar_sinalizadores_processuais(grupos: list) -> dict:
    eventos = detectar_eventos_cautelares(grupos)

    if eventos["tem_transito_julgado"]:
        fase = "Sentenciado com trânsito em julgado"
    elif eventos["tem_extincao_punibilidade"] or eventos.get("tem_cumprimento_sursis") or eventos.get("tem_cumprimento_anpp"):
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

    if eventos["tem_extincao_punibilidade"] or eventos["tem_transito_julgado"]:
        status = "EXTINTA (cessou com sentença/extinção)"
    elif eventos.get("tem_cumprimento_sursis") or eventos.get("tem_cumprimento_anpp"):
        status = "EXTINTA (sursis/ANPP cumprido)"
    elif eventos["tem_revogacao"]:
        status = "REVOGADA"
    elif eventos["tem_preventiva_decretada"]:
        status = "CONVERTIDA EM PREVENTIVA"
    elif eventos["tem_cautelar_319"] or eventos["tem_liberdade_provisoria"]:
        status = "PROVAVELMENTE ATIVA"
    elif eventos["tem_sursis_processual"] or eventos["tem_anpp"]:
        status = "VERIFICAR (sursis/ANPP — pode ter cumprido)"
    else:
        status = "SEM CAUTELAR DETECTADA"

    return {
        "fase_aparente": fase,
        "provavel_status_cautelar": status,
        "eventos": eventos,
    }
