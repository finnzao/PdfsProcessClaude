"""
common/utils_io.py — Helpers de I/O, formatacao e parsing de nomes.
"""

import json
import re
from pathlib import Path


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def ler_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default if default is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def salvar_json(path, dados):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def formato_tamanho(bytes_):
    for unidade in ["B", "KB", "MB", "GB"]:
        if bytes_ < 1024:
            return f"{bytes_:.1f}{unidade}"
        bytes_ /= 1024
    return f"{bytes_:.1f}TB"


def formato_tempo(segundos):
    if segundos < 60:
        return f"{segundos:.1f}s"
    minutos = int(segundos // 60)
    seg = int(segundos % 60)
    if minutos < 60:
        return f"{minutos}m{seg:02d}s"
    horas = minutos // 60
    minutos = minutos % 60
    return f"{horas}h{minutos:02d}m{seg:02d}s"


def extrair_numero_processo(nome_arquivo: str) -> str:
    """Extrai numero CNJ de nome de arquivo PDF ou MD."""
    padrao = re.search(
        r"(\d{7})[-_.]?(\d{2})[_.](\d{4})[_.](\d{1,2})[_.](\d{2})[_.](\d{4})",
        nome_arquivo,
    )
    if padrao:
        return (
            f"{padrao.group(1)}-{padrao.group(2)}."
            f"{padrao.group(3)}.{padrao.group(4)}."
            f"{padrao.group(5)}.{padrao.group(6)}"
        )
    return Path(nome_arquivo).stem


def num_para_arquivo(numero: str, ext: str = ".md") -> str:
    return numero.replace(".", "_").replace("-", "_") + ext


def formatar_doc_ids(doc_ids):
    """
    Consolida lista de [(num, pag)...] em notacao compacta.
    """
    if not doc_ids:
        return ""

    ordem = []
    por_num = {}
    for item in doc_ids:
        if not item:
            continue
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            num, pag = item[0], item[1]
        else:
            continue
        try:
            p = int(pag)
        except (ValueError, TypeError):
            continue
        if num not in por_num:
            por_num[num] = []
            ordem.append(num)
        por_num[num].append(p)

    partes = []
    for num in ordem:
        pags = sorted(set(por_num[num]))
        if not pags:
            continue
        ranges = []
        i = 0
        while i < len(pags):
            j = i
            while j + 1 < len(pags) and pags[j + 1] == pags[j] + 1:
                j += 1
            if i == j:
                ranges.append(f"{pags[i]}")
            else:
                ranges.append(f"{pags[i]}-{pags[j]}")
            i = j + 1
        partes.append(f"Num. {num} (p.{','.join(ranges)})")

    return ", ".join(partes)


def primeira_linha(texto: str, max_chars: int = 120) -> str:
    for linha in texto.split("\n"):
        limpa = linha.strip().strip("#").strip("*").strip()
        if len(limpa) > 10:
            return limpa[:max_chars]
    return texto[:max_chars]
