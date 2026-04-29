"""
utils/ — Constantes e helpers reutilizáveis.

Este pacote concentra dados estáticos (regex, listas de tipos, palavras-chave)
para que os módulos principais (extrair_processos.py, etc.) fiquem enxutos
e focados na lógica de pipeline.

Submódulos:
    constantes_pje      — lixo PJe/Sinesp e regex de IDs de documento
    tipos_pecas         — classificação de peças processuais
    sinalizadores       — detecção de cautelares, datas e dados pessoais
    formatadores        — helpers de formatação (datas, CPFs, etc.)
"""

from utils.constantes_pje import (
    PADROES_LIXO,
    RE_NUM_PAG,
    RE_NUM_ONLY,
    extrair_doc_id,
    limpar_texto,
)
from utils.tipos_pecas import (
    TIPOS_PECAS,
    PECAS_COMPLETAS,
    PECAS_RESUMO,
    PECAS_DESCARTE,
    classificar_peca,
)
from utils.sinalizadores import (
    RE_CPF,
    RE_TELEFONE,
    RE_DATA,
    RE_DATA_EXTENSO,
    RE_CEP,
    RE_RG,
    PALAVRAS_CAUTELAR,
    PALAVRAS_REVOGACAO,
    PALAVRAS_EXTINCAO,
    PALAVRAS_TRANSITO,
    PALAVRAS_PRESO,
    PALAVRAS_REU,
    PALAVRAS_VITIMA,
    detectar_dados_pessoais,
    detectar_eventos_cautelares,
    detectar_sinalizadores_processuais,
)
from utils.formatadores import (
    formatar_cpf,
    formatar_telefone,
    formatar_cep,
    primeira_linha,
    extrair_numero_processo,
)

__all__ = [
    # constantes_pje
    "PADROES_LIXO", "RE_NUM_PAG", "RE_NUM_ONLY",
    "extrair_doc_id", "limpar_texto",
    # tipos_pecas
    "TIPOS_PECAS", "PECAS_COMPLETAS", "PECAS_RESUMO", "PECAS_DESCARTE",
    "classificar_peca",
    # sinalizadores
    "RE_CPF", "RE_TELEFONE", "RE_DATA", "RE_DATA_EXTENSO", "RE_CEP", "RE_RG",
    "PALAVRAS_CAUTELAR", "PALAVRAS_REVOGACAO", "PALAVRAS_EXTINCAO",
    "PALAVRAS_TRANSITO", "PALAVRAS_PRESO", "PALAVRAS_REU", "PALAVRAS_VITIMA",
    "detectar_dados_pessoais", "detectar_eventos_cautelares",
    "detectar_sinalizadores_processuais",
    # formatadores
    "formatar_cpf", "formatar_telefone", "formatar_cep",
    "primeira_linha", "extrair_numero_processo",
]
