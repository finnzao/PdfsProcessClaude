#!/usr/bin/env python3
"""
consolidar_base.py — Classe base para consolidação de resultados.
Cada service herda e customiza: formato de saída, estatísticas.
"""

import csv
import json
from pathlib import Path
from collections import Counter
from datetime import datetime


class ConsolidarBase:
    """Classe base para consolidar resultados de um service."""

    SERVICE_NAME = "base"

    def __init__(self, service_dir: Path, result_dir: Path):
        self.service_dir = service_dir
        self.resultados_dir = service_dir / "resultados"
        self.result_dir = result_dir
        self.result_dir.mkdir(parents=True, exist_ok=True)

    def encontrar_resultados(self, pattern="*"):
        return sorted(self.resultados_dir.glob(pattern))

    def consolidar(self):
        """Override nos services para customizar a consolidação."""
        raise NotImplementedError

    def consolidar_csvs(self, pattern="analise_*.csv", saida_nome="relatorio_final.csv",
                        ordenar_por=None):
        """Consolidação genérica de CSVs."""
        csvs = sorted(self.resultados_dir.glob(pattern))

        if not csvs:
            print(f"  ❌ Nenhum resultado em {self.resultados_dir}/")
            return None

        print(f"  {len(csvs)} arquivos encontrados")

        todas_linhas = []
        headers = None

        for csv_path in csvs:
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    if headers is None:
                        headers = reader.fieldnames
                    for row in reader:
                        row["arquivo_origem"] = csv_path.name
                        todas_linhas.append(row)
            except Exception as e:
                print(f"  ⚠️  Erro: {csv_path.name}: {e}")

        if not todas_linhas:
            print("  ❌ Nenhuma linha de dados.")
            return None

        if ordenar_por:
            todas_linhas.sort(key=ordenar_por)

        if headers and "arquivo_origem" not in headers:
            headers.append("arquivo_origem")

        saida = self.result_dir / saida_nome
        with open(saida, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers or todas_linhas[0].keys())
            writer.writeheader()
            writer.writerows(todas_linhas)

        print(f"  ✅ {len(todas_linhas)} registros → {saida}")
        return saida
