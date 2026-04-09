#!/usr/bin/env python3
"""
utils.py — Utilitários compartilhados entre todos os services.
"""

import re
import csv
import json
from pathlib import Path
from datetime import datetime

# ============================================================
# CAMINHOS DO PROJETO (relativos à raiz)
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent
DIR_PDFS = PROJECT_ROOT / "pdfs"
DIR_TEXTOS = PROJECT_ROOT / "textos_extraidos"
DIR_FILES = PROJECT_ROOT / "files"
DIR_RESULT = PROJECT_ROOT / "result"
DIR_SERVICES = PROJECT_ROOT / "services"

CSV_PROCESSOS = DIR_FILES / "processos_crime_parados_mais_que_100_dias.csv"


def carregar_csv_processos():
    """Carrega o CSV de processos e retorna dict {numero: row}."""
    processos = {}
    if not CSV_PROCESSOS.exists():
        return processos
    with open(CSV_PROCESSOS, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            num = row.get('Número do Processo', '').strip()
            if num and num not in processos:
                processos[num] = row
    return processos


def num_para_arquivo(numero, ext=".txt"):
    """Converte número CNJ para nome de arquivo."""
    return numero.replace('.', '_').replace('-', '_') + ext


def arquivo_para_num(nome_arquivo):
    """Converte nome de arquivo de volta para número CNJ."""
    stem = Path(nome_arquivo).stem
    parts = stem.split('_')
    if len(parts) >= 5:
        p1 = f"{parts[0]}-{parts[1]}"
        return f"{p1}.{parts[2]}.{parts[3]}.{parts[4]}.{parts[5]}"
    return stem


def extrair_nome_do_csv_mov(ultima_mov):
    """Extrai nome do réu do campo 'Última Movimentação' do CSV."""
    m = re.search(r'Decorrido prazo de\s+(.+?)\s+em\s+\d', ultima_mov, re.IGNORECASE)
    if m:
        nome = m.group(1).strip()
        skip = ['MINISTERIO', 'DELEGACIA', 'DT RIO', 'SECRETARIA',
                'AÇÃO SOCIAL', 'A SOCIEDADE', 'MP ', 'MINISTÉRIO',
                'DELEGACIA TERRITORIAL']
        if not any(s in nome.upper() for s in skip):
            return nome
    return None


def calcular_urgencia(row):
    """Calcula score e nível de urgência de um processo."""
    dias = int(row.get("Dias", 0))
    assunto = row.get("Assunto", "").lower()
    classe = row.get("Classe", "")

    criticos = ["homicídio", "latrocínio", "estupro", "vulnerável"]
    altos = ["tráfico", "roubo", "armas", "violência doméstica",
             "mulher", "medida protetiva", "descumprimento"]

    score = dias
    if any(kw in assunto for kw in criticos) or classe == "Juri":
        score += 2000
    elif any(kw in assunto for kw in altos):
        score += 1000
    if dias > 730:
        score += 500
    elif dias > 365:
        score += 300

    if score >= 1500:
        return score, "CRITICA"
    elif score >= 800:
        return score, "ALTA"
    elif score >= 400:
        return score, "MEDIA"
    else:
        return score, "BAIXA"


def listar_textos_extraidos():
    """Retorna dict {nome_stem: path} dos textos extraídos."""
    txts = {}
    if DIR_TEXTOS.exists():
        for f in DIR_TEXTOS.iterdir():
            if f.suffix in ('.txt', '.md'):
                txts[f.stem] = f
    return txts


def agora_iso():
    return datetime.now().isoformat()


def agora_br():
    return datetime.now().strftime('%d/%m/%Y %H:%M')
