#!/usr/bin/env python3
"""
consolidar.py — Junta todos os CSVs de resultados/ em um relatório final.

USO:
    python3 scripts/consolidar.py

SAÍDA:
    relatorio_final.csv          — Todos os processos analisados, ordenados por urgência
    resumo_estatisticas.txt      — Estatísticas consolidadas
"""

import csv
import json
import os
from pathlib import Path
from collections import Counter
from datetime import datetime

DIR_RESULTADOS = Path("resultados")
CHECKPOINT_FILE = Path("checkpoint.json")


def main():
    print("=" * 60)
    print("CONSOLIDAÇÃO DOS RESULTADOS")
    print("=" * 60)

    # Encontrar todos os CSVs de resultado
    csvs = sorted(DIR_RESULTADOS.glob("analise_*.csv"))

    if not csvs:
        print("  ❌ Nenhum arquivo de resultado encontrado em resultados/")
        print("     Execute os comandos no Claude Code primeiro.")
        return

    print(f"  📄 {len(csvs)} arquivos encontrados")

    # Ler e juntar todos os CSVs
    todas_linhas = []
    headers = None
    erros = []

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
            erros.append(f"{csv_path.name}: {e}")

    if erros:
        print(f"  ⚠️  Erros ao ler {len(erros)} arquivos:")
        for err in erros:
            print(f"    - {err}")

    if not todas_linhas:
        print("  ❌ Nenhuma linha de dados encontrada.")
        return

    print(f"  📊 {len(todas_linhas)} processos consolidados")

    # Ordenar por urgência
    ordem_urgencia = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2, "BAIXA": 3}
    todas_linhas.sort(key=lambda x: (
        ordem_urgencia.get(x.get("urgencia", "BAIXA"), 4),
        -int(x.get("dias_parado", 0)) if x.get("dias_parado", "").isdigit() else 0
    ))

    # Adicionar coluna de arquivo de origem ao header
    if headers and "arquivo_origem" not in headers:
        headers.append("arquivo_origem")

    # Salvar relatório final
    saida = Path("relatorio_final.csv")
    with open(saida, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers or todas_linhas[0].keys())
        writer.writeheader()
        writer.writerows(todas_linhas)

    print(f"  ✅ Relatório salvo: {saida}")

    # === ESTATÍSTICAS ===
    urgencias = Counter(r.get("urgencia", "?") for r in todas_linhas)
    classes = Counter(r.get("classe", "?") for r in todas_linhas)
    prescricao = Counter(r.get("risco_prescricao", "?").upper()[:3] for r in todas_linhas)

    stats = []
    stats.append("=" * 60)
    stats.append("ESTATÍSTICAS DA ANÁLISE")
    stats.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    stats.append("=" * 60)
    stats.append(f"\nTotal de processos analisados: {len(todas_linhas)}")
    stats.append(f"Arquivos de resultado: {len(csvs)}")

    stats.append("\nPor urgência:")
    for urg in ["CRITICA", "ALTA", "MEDIA", "BAIXA"]:
        qtd = urgencias.get(urg, 0)
        pct = qtd / len(todas_linhas) * 100
        barra = "█" * int(pct // 2)
        stats.append(f"  {urg:8s}: {qtd:3d} ({pct:5.1f}%) {barra}")

    stats.append("\nPor classe processual:")
    for cls, qtd in classes.most_common():
        stats.append(f"  {cls:20s}: {qtd:3d}")

    stats.append("\nRisco de prescrição:")
    for k, v in prescricao.most_common():
        stats.append(f"  {k}: {v}")

    stats_text = "\n".join(stats)
    stats_path = Path("resumo_estatisticas.txt")
    with open(stats_path, 'w', encoding='utf-8') as f:
        f.write(stats_text)

    print(f"  📈 Estatísticas: {stats_path}")
    print(f"\n{stats_text}")

    # Checkpoint
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r') as f:
            ck = json.load(f)
        print(f"\n  Sessões realizadas: {len(ck.get('sessoes', []))}")
        print(f"  Comandos executados: {len(ck.get('comandos_concluidos', []))}")

    print(f"\n{'=' * 60}")
    print(f"  ✅ CONCLUÍDO!")
    print(f"  Relatório: {saida}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
