"""utils — pacotes auxiliares para extração estruturada."""

from utils.tipos_pecas import (
    classificar_peca, TIPOS_PECAS, PECAS_COMPLETAS, PECAS_RESUMO,
    PECAS_DESCARTE, PECAS_FONTE_CAUTELAR,
)
from utils.extrator_qualificacao import (
    extrair_qualificacao_reu, DadosReu,
)
from utils.extrator_cautelar import (
    extrair_cautelar, DadosCautelar,
)

__all__ = [
    "classificar_peca", "TIPOS_PECAS",
    "PECAS_COMPLETAS", "PECAS_RESUMO", "PECAS_DESCARTE", "PECAS_FONTE_CAUTELAR",
    "extrair_qualificacao_reu", "DadosReu",
    "extrair_cautelar", "DadosCautelar",
]
