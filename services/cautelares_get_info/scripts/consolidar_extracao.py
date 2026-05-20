"""scripts/consolidar_extracao.py — Consolida resultados de extracao em planilha."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from services.cautelares_get_info.scripts.consolidar import (
    carregar_jsons,
    consolidar_para_xlsx,
)

ROOT = Path(__file__).parent.parent.parent.parent
SERVICE_DIR = ROOT / "services" / "cautelares_get_info"
DIR_EXTRACAO = SERVICE_DIR / "resultados" / "extracao"
CONTROLE_PATH = SERVICE_DIR / "processos_claude_code.json"
SAIDA_XLSX = SERVICE_DIR / "resultados" / "custodiados.xlsx"


def carregar_processos() -> list[dict]:
    """Prefere o controle global; cai para os extracao_NNN.json."""
    if CONTROLE_PATH.exists():
        try:
            d = json.loads(CONTROLE_PATH.read_text(encoding="utf-8"))
            return list(d.get("processos", {}).values())
        except json.JSONDecodeError:
            pass
    return carregar_jsons(DIR_EXTRACAO, "extracao_*.json")


def consolidar() -> None:
    processos = carregar_processos()
    if not processos:
        print("  Nenhum processo encontrado para consolidar.")
        return

    SAIDA_XLSX.parent.mkdir(parents=True, exist_ok=True)
    consolidar_para_xlsx(processos, SAIDA_XLSX, nome_aba="Custodiados")
    print(f"  Total: {len(processos)} processos consolidados.")


if __name__ == "__main__":
    consolidar()
