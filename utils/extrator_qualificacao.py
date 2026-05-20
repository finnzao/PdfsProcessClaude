"""utils/extrator_qualificacao.py — Extracao de qualificacao do reu/custodiado."""

import re

from utils.constantes_pje import REGEXES_QUALIFICACAO
from utils.formatadores import (
    formatar_cpf,
    formatar_data_br,
    formatar_telefone,
    normalizar_nome,
)


def _grab(texto: str, padrao_str: str, flags=re.IGNORECASE) -> str:
    m = re.search(padrao_str, texto, flags)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def extrair_qualificacao(texto: str) -> dict:
    """
    Extrai dados de qualificacao a partir do texto bruto.
    Retorna dict com chaves: nome, alcunha, cpf, rg, data_nascimento,
    filiacao_mae, filiacao_pai, endereco, telefone, profissao, estado_civil,
    naturalidade, escolaridade.
    """
    if not texto:
        return {k: "" for k in REGEXES_QUALIFICACAO}

    out = {}

    out["nome"] = normalizar_nome(_grab(texto, REGEXES_QUALIFICACAO["nome"]))
    out["alcunha"] = _grab(texto, REGEXES_QUALIFICACAO["alcunha"])

    cpf_bruto = _grab(texto, REGEXES_QUALIFICACAO["cpf"])
    out["cpf"] = formatar_cpf(cpf_bruto)

    out["rg"] = _grab(texto, REGEXES_QUALIFICACAO["rg"])
    out["data_nascimento"] = formatar_data_br(
        _grab(texto, REGEXES_QUALIFICACAO["data_nascimento"])
    )
    out["filiacao_mae"] = normalizar_nome(_grab(texto, REGEXES_QUALIFICACAO["filiacao_mae"]))
    out["filiacao_pai"] = normalizar_nome(_grab(texto, REGEXES_QUALIFICACAO["filiacao_pai"]))
    out["endereco"] = _grab(texto, REGEXES_QUALIFICACAO["endereco"])

    m_tel = re.search(REGEXES_QUALIFICACAO["telefone"], texto)
    if m_tel:
        ddd, meio, fim = m_tel.group(1), m_tel.group(2), m_tel.group(3)
        out["telefone"] = formatar_telefone(f"{ddd}{meio}{fim}")
    else:
        out["telefone"] = ""

    out["profissao"] = _grab(texto, REGEXES_QUALIFICACAO["profissao"]).lower().strip()
    out["estado_civil"] = _grab(texto, REGEXES_QUALIFICACAO["estado_civil"]).lower().strip()
    out["naturalidade"] = _grab(texto, REGEXES_QUALIFICACAO["naturalidade"])
    out["escolaridade"] = _grab(texto, REGEXES_QUALIFICACAO["escolaridade"])

    return out
