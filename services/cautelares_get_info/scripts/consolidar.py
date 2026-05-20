"""scripts/consolidar.py — Consolidador generico de jsons em xlsx."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def carregar_jsons(diretorio: Path, padrao: str = "*.json") -> list[dict]:
    if not diretorio.exists():
        return []
    out = []
    for p in sorted(diretorio.glob(padrao)):
        try:
            dados = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(dados, list):
            out.extend(dados)
        elif isinstance(dados, dict):
            out.append(dados)
    return out


def flatten_dict(d: dict, prefix: str = "") -> dict:
    """Achata dict aninhado em chaves separadas por '.'."""
    out = {}
    for k, v in d.items():
        chave = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten_dict(v, chave))
        elif isinstance(v, list):
            out[chave] = "; ".join(str(x) for x in v)
        else:
            out[chave] = v
    return out


def consolidar_para_xlsx(itens: list[dict], saida: Path, nome_aba: str = "Dados") -> None:
    """Salva itens em xlsx, achatando dicts aninhados."""
    try:
        from openpyxl import Workbook
    except ImportError:
        print("  openpyxl ausente; instale via 'pip install openpyxl'")
        return

    if not itens:
        print("  Sem itens para consolidar.")
        return

    flat = [flatten_dict(it) for it in itens]
    todas_chaves = []
    vistos = set()
    for it in flat:
        for k in it.keys():
            if k not in vistos:
                vistos.add(k)
                todas_chaves.append(k)

    wb = Workbook()
    ws = wb.active
    ws.title = nome_aba[:30]
    ws.append(todas_chaves)
    for it in flat:
        ws.append([it.get(k, "") for k in todas_chaves])

    saida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(saida)
    print(f"  xlsx salvo em {saida} ({len(itens)} linhas, {len(todas_chaves)} colunas)")
