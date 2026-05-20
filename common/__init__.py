"""common — Pipeline de extracao PDF -> markdown."""

from common.extrator_pdf import (
    processar_pdf,
    cache_key_arquivo,
    versao_utils,
    ResultadoExtracao,
)
from common.utils_io import (
    extrair_numero_processo,
    num_para_arquivo,
    formatar_doc_ids,
    primeira_linha,
)
from common.classificador_pecas import (
    classificar_peca,
    classificar_peca_com_score,
    PECAS_COMPLETAS,
    PECAS_RESUMO,
    PECAS_DESCARTE,
    PECAS_FONTE_CAUTELAR,
)
from common.limpeza_pje import limpar_texto, extrair_doc_id
from common.sinalizadores_proc import (
    detectar_dados_pessoais,
    detectar_sinalizadores_processuais,
    detectar_eventos_cautelares,
)

__all__ = [
    "processar_pdf",
    "cache_key_arquivo",
    "versao_utils",
    "ResultadoExtracao",
    "extrair_numero_processo",
    "num_para_arquivo",
    "formatar_doc_ids",
    "primeira_linha",
    "classificar_peca",
    "classificar_peca_com_score",
    "PECAS_COMPLETAS",
    "PECAS_RESUMO",
    "PECAS_DESCARTE",
    "PECAS_FONTE_CAUTELAR",
    "limpar_texto",
    "extrair_doc_id",
    "detectar_dados_pessoais",
    "detectar_sinalizadores_processuais",
    "detectar_eventos_cautelares",
]
