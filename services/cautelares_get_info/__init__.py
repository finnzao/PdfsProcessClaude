"""scripts — código executável do serviço cautelares_get_info."""

from services.cautelares_get_info.scripts.pre_extracao import processar_md, processar_lote
from services.cautelares_get_info.scripts.consolidar import consolidar, COLUNAS_DTO

__all__ = ["processar_md", "processar_lote", "consolidar", "COLUNAS_DTO"]
