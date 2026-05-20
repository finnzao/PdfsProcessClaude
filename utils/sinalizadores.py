"""utils/sinalizadores.py — Atalhos para inferencia de status cautelar e fase."""

from common.sinalizadores_proc import detectar_sinalizadores_processuais


def detectar_status_cautelar(grupos: list) -> str:
    """Retorna o status provavel da cautelar (string descritiva)."""
    sin = detectar_sinalizadores_processuais(grupos)
    return sin.get("provavel_status_cautelar", "SEM CAUTELAR DETECTADA")


def detectar_fase_processual(grupos: list) -> str:
    """Retorna a fase aparente do processo (string descritiva)."""
    sin = detectar_sinalizadores_processuais(grupos)
    return sin.get("fase_aparente", "Sem eventos de cautelar identificados")
