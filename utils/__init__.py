"""utils — Constantes, formatadores e extratores específicos do PJe/TJBA."""

from utils.constantes_pje import (
    UF_BR,
    TIPOS_CAUTELARES_LISTA,
    PRAZO_TERMO_DIAS,
    REGEXES_QUALIFICACAO,
)
from utils.tipos_pecas import (
    TIPO_LISTA_COMPLETA,
    TIPO_PECA_PARA_NORMALIZADO,
    normalizar_tipo_peca,
)
from utils.formatadores import (
    formatar_cpf,
    formatar_telefone,
    formatar_data_br,
    normalizar_nome,
    titulizar,
)
from utils.sinalizadores import (
    detectar_status_cautelar,
    detectar_fase_processual,
)
from utils.extrator_cautelar import extrair_cautelares
from utils.extrator_qualificacao import extrair_qualificacao

__all__ = [
    "UF_BR",
    "TIPOS_CAUTELARES_LISTA",
    "PRAZO_TERMO_DIAS",
    "REGEXES_QUALIFICACAO",
    "TIPO_LISTA_COMPLETA",
    "TIPO_PECA_PARA_NORMALIZADO",
    "normalizar_tipo_peca",
    "formatar_cpf",
    "formatar_telefone",
    "formatar_data_br",
    "normalizar_nome",
    "titulizar",
    "detectar_status_cautelar",
    "detectar_fase_processual",
    "extrair_cautelares",
    "extrair_qualificacao",
]
