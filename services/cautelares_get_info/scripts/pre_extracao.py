"""scripts/pre_extracao.py — Identifica processos com cautelares ativas a partir dos .md."""

from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent.parent.parent
DIR_PRE_EXTRAIDO = ROOT / "pre_extraido"
SAIDA = ROOT / "services" / "cautelares_get_info" / "pre_extracao.json"

# Sinais de cautelar ATIVA no markdown gerado
RE_SINAL_CAUTELAR_ATIVA = re.compile(
    r"\*\*Prov[áa]vel status da cautelar\*\*:\s*(PROVAVELMENTE ATIVA|CONVERTIDA EM PREVENTIVA|VERIFICAR)",
    re.I,
)


def _ler_numero_processo(md_path: Path) -> str:
    """Le primeira linha '# NUMERO' do markdown."""
    try:
        primeira = md_path.read_text(encoding="utf-8").split("\n", 1)[0]
        return primeira.lstrip("# ").strip()
    except Exception:
        return ""


def _ler_status(md_path: Path) -> str:
    try:
        texto = md_path.read_text(encoding="utf-8")
    except Exception:
        return ""
    m = RE_SINAL_CAUTELAR_ATIVA.search(texto)
    return m.group(1) if m else ""


def listar_elegiveis() -> list[dict]:
    """Retorna lista de processos com cautelar ativa/duvidosa."""
    if not DIR_PRE_EXTRAIDO.exists():
        return []
    elegiveis = []
    for md in sorted(DIR_PRE_EXTRAIDO.glob("*.md")):
        numero = _ler_numero_processo(md)
        status = _ler_status(md)
        if not numero or not status:
            continue
        elegiveis.append({
            "numero_processo": numero,
            "arquivo_md": md.name,
            "status_cautelar": status,
        })
    return elegiveis


def salvar_pre_extracao(itens: list[dict]) -> None:
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(
        json.dumps(
            {
                "gerado_em": datetime.now().isoformat(),
                "total": len(itens),
                "itens": itens,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )


def main():
    itens = listar_elegiveis()
    salvar_pre_extracao(itens)
    print(f"  {len(itens)} processos elegiveis salvos em {SAIDA}")


if __name__ == "__main__":
    main()
