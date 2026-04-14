#!/usr/bin/env python3
"""utils.py — Caminhos do projeto e funções utilitárias."""

import re, csv, json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
DIR_PDFS = PROJECT_ROOT / "pdfs"
DIR_TEXTOS = PROJECT_ROOT / "textos_extraidos"
DIR_FILES = PROJECT_ROOT / "files"
DIR_RESULT = PROJECT_ROOT / "result"
CSV_PROCESSOS = DIR_FILES / "processos_crime_parados_mais_que_100_dias.csv"


def carregar_csv_processos():
    """CSV de processos → {numero: row}."""
    if not CSV_PROCESSOS.exists(): return {}
    proc = {}
    with open(CSV_PROCESSOS, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            num = row.get('Número do Processo', '').strip()
            if num and num not in proc: proc[num] = row
    return proc


def num_para_arquivo(numero, ext=".md"):
    """CNJ → nome de arquivo."""
    return numero.replace('.', '_').replace('-', '_') + ext


def arquivo_para_num(nome):
    """Nome de arquivo → CNJ."""
    parts = Path(nome).stem.split('_')
    if len(parts) >= 6:
        return f"{parts[0]}-{parts[1]}.{parts[2]}.{parts[3]}.{parts[4]}.{parts[5]}"
    return Path(nome).stem


def calcular_urgencia(row):
    """Score e nível (CRITICA/ALTA/MEDIA/BAIXA) baseado em dias parado e crime."""
    dias = int(row.get("Dias", 0))
    assunto = row.get("Assunto", "").lower()
    classe = row.get("Classe", "")

    score = dias
    if any(k in assunto for k in ["homicídio","latrocínio","estupro","vulnerável"]) or classe == "Juri":
        score += 2000
    elif any(k in assunto for k in ["tráfico","roubo","armas","violência doméstica","mulher","medida protetiva"]):
        score += 1000
    if dias > 730: score += 500
    elif dias > 365: score += 300

    if score >= 1500: return score, "CRITICA"
    if score >= 800: return score, "ALTA"
    if score >= 400: return score, "MEDIA"
    return score, "BAIXA"


def listar_textos_extraidos():
    """{stem: path} dos .md extraídos."""
    if not DIR_TEXTOS.exists(): return {}
    return {f.stem: f for f in DIR_TEXTOS.iterdir() if f.suffix in ('.txt', '.md')}

def agora_iso(): return datetime.now().isoformat()
def agora_br(): return datetime.now().strftime('%d/%m/%Y %H:%M')
