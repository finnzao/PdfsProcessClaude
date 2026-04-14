#!/usr/bin/env python3
"""consolidar_base.py — Junta resultados parciais de um service."""

import csv
from pathlib import Path


class ConsolidarBase:
    SERVICE_NAME = "base"

    def __init__(self, service_dir: Path, result_dir: Path):
        self.resultados_dir = service_dir / "resultados"
        self.result_dir = result_dir
        self.result_dir.mkdir(parents=True, exist_ok=True)

    def consolidar(self): raise NotImplementedError

    def consolidar_csvs(self, pattern="*.csv", saida_nome="relatorio_final.csv", ordenar_por=None):
        """Junta CSVs de resultado num único arquivo."""
        csvs = sorted(self.resultados_dir.glob(pattern))
        if not csvs: print(f"  ❌ Nenhum resultado."); return None
        print(f"  {len(csvs)} arquivos")

        linhas, headers = [], None
        for cp in csvs:
            try:
                with open(cp, 'r', encoding='utf-8') as f:
                    rd = csv.DictReader(f)
                    if not headers: headers = rd.fieldnames
                    for row in rd: row["arquivo_origem"] = cp.name; linhas.append(row)
            except Exception as e: print(f"  ⚠️ {cp.name}: {e}")

        if not linhas: print("  ❌ Sem dados."); return None
        if ordenar_por: linhas.sort(key=ordenar_por)
        if headers and "arquivo_origem" not in headers: headers.append("arquivo_origem")

        saida = self.result_dir / saida_nome
        with open(saida, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=headers or linhas[0].keys())
            w.writeheader(); w.writerows(linhas)
        print(f"  OK {len(linhas)} registros -> {saida}")
        return saida
