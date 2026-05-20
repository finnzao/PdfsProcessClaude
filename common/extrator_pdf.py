"""
common/extrator_pdf.py — Pipeline de extracao PDF -> markdown.

Melhorias principais:
  - pymupdf.Document aberto uma unica vez por PDF (nao reabre por pagina)
  - OCR adaptativo: Otsu+PSM3 -> PSM6 -> PSM4 com fallback gradual
  - Deskew via Hough/projecao antes do OCR
  - Cache granular por pagina (hash + dpi + psm)
  - Binarizacao via cv2.threshold(THRESH_OTSU) quando OpenCV disponivel
  - Classificador multi-janela para textos longos
  - Capa PJe com score probabilistico, zona cinza e fallback de metadados
  - Agrupamento que penaliza gaps grandes e usa doc_id como separador forte
  - Retorno como dataclass ResultadoExtracao
"""

from __future__ import annotations

import hashlib
import inspect
import io
import json
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from common.classificador_pecas import (
    PECAS_COMPLETAS,
    PECAS_DESCARTE,
    PECAS_RESUMO,
    classificar_peca_com_score,
)
from common.limpeza_pje import limpar_texto, extrair_doc_id
from common.sinalizadores_proc import (
    detectar_dados_pessoais,
    detectar_sinalizadores_processuais,
)
from common.utils_io import (
    extrair_numero_processo,
    formatar_doc_ids,
    primeira_linha,
    salvar_json,
)


# ========================================================
#   Constantes e cache global
# ========================================================
DEFAULT_OCR_THRESHOLD = 80
MIN_RAZAO_VALIDOS = 0.55
MAX_DENSIDADE_CORRUPCAO = 0.02

# Cache de paginas OCRizadas {chave: texto}. Vive enquanto o processo Python roda.
_CACHE_OCR_PAGINA: dict[str, str] = {}
_CACHE_OCR_MAX = 4000  # entradas


def _cache_ocr_set(chave: str, valor: str) -> None:
    if len(_CACHE_OCR_PAGINA) >= _CACHE_OCR_MAX:
        # Evicta as mais antigas (50% das entradas)
        for k in list(_CACHE_OCR_PAGINA.keys())[: _CACHE_OCR_MAX // 2]:
            _CACHE_OCR_PAGINA.pop(k, None)
    _CACHE_OCR_PAGINA[chave] = valor


CHARS_CORROMPIDOS = re.compile(r"[∞ÈÁ„‡ïÙ˙ıÌı‰ÒÏü¿¬«¶®©ª¯±²³µ¸¹º»¼½¾]")
RE_CHARS_VALIDOS = re.compile(
    r"[a-zA-ZáéíóúâêôãõàèìòùäëïöüçñÁÉÍÓÚÂÊÔÃÕÀÈÌÒÙÄËÏÖÜÇÑ0-9 ]"
)


# ========================================================
#   Cache e versionamento
# ========================================================

def _md5_arquivo(path: str | Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(8192), b""):
            h.update(bloco)
    return h.hexdigest()


def versao_utils() -> str:
    """Hash dos modulos que afetam saida — invalida cache automaticamente."""
    from common import classificador_pecas, limpeza_pje, sinalizadores_proc
    h = hashlib.md5()
    for mod in (classificador_pecas, limpeza_pje, sinalizadores_proc):
        h.update(inspect.getsource(mod).encode())
    return h.hexdigest()[:8]


def cache_key_arquivo(pdf_path: str | Path) -> str:
    return f"{_md5_arquivo(pdf_path)}_{versao_utils()}"


# ========================================================
#   Dataclass de retorno
# ========================================================

@dataclass
class ResultadoExtracao:
    numero: str
    arquivo: str
    status: str = "OK"
    arquivo_saida: str = ""
    total_paginas: int = 0
    paginas_ocr: int = 0
    classe: str = ""
    assunto: str = ""
    pecas: int = 0
    chars_bruto: int = 0
    chars_limpo: int = 0
    tokens_aprox: int = 0
    reducao_pct: float = 0.0
    cache_key: str = ""
    fase_aparente: str = ""
    provavel_status_cautelar: str = ""
    erro: str = ""
    # Metricas de observabilidade
    metricas: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ========================================================
#   Heuristicas de OCR
# ========================================================

def _razao_chars_validos(t: str) -> float:
    if not t:
        return 0.0
    return len(RE_CHARS_VALIDOS.findall(t)) / len(t)


def _densidade_corrupcao(t: str) -> float:
    if not t:
        return 0.0
    return len(CHARS_CORROMPIDOS.findall(t)) / len(t)


def deve_ocrizar(texto_nativo: str, threshold: int = DEFAULT_OCR_THRESHOLD) -> tuple[bool, str]:
    t = (texto_nativo or "").strip()

    if len(t) < threshold:
        return True, f"texto curto ({len(t)} < {threshold} chars)"

    if _densidade_corrupcao(t) > MAX_DENSIDADE_CORRUPCAO:
        return True, "encoding corrompido (>2% chars invalidos)"

    if _razao_chars_validos(t) < MIN_RAZAO_VALIDOS:
        return True, f"razao chars validos < {MIN_RAZAO_VALIDOS}"

    palavras_reais = sum(
        1 for p in t.split()
        if len(p) >= 3 and re.match(r"^[A-Za-záéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ]+$", p)
    )
    if palavras_reais < 15:
        return True, f"poucas palavras reais ({palavras_reais})"

    return False, "texto nativo aceitavel"


# ========================================================
#   Pre-processamento de imagem (Otsu via OpenCV ou fallback)
# ========================================================

def _otsu_opencv(img):
    """Otsu via cv2.threshold(THRESH_OTSU). Retorna PIL.Image em modo L."""
    try:
        import cv2
        import numpy as np
        from PIL import Image

        if img.mode != "L":
            img = img.convert("L")
        arr = np.array(img)
        _, binarizada = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return Image.fromarray(binarizada, mode="L")
    except Exception:
        return None


def _otsu_numpy(img):
    """Fallback puro-Python+NumPy para Otsu."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return img

    if img.mode != "L":
        img = img.convert("L")
    arr = np.array(img)

    hist, _ = np.histogram(arr, bins=256, range=(0, 256))
    total = arr.size
    sum_total = np.dot(np.arange(256), hist)
    sum_b = 0.0
    w_b = 0
    max_var = 0.0
    threshold = 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > max_var:
            max_var = var
            threshold = t

    thr_adj = min(255, threshold + 10)
    binarizada = (arr >= thr_adj).astype(np.uint8) * 255
    return Image.fromarray(binarizada, mode="L")


def _aplicar_otsu(img):
    """Tenta OpenCV; cai para numpy; ultima opcao devolve original."""
    res = _otsu_opencv(img)
    if res is not None:
        return res
    try:
        return _otsu_numpy(img)
    except Exception:
        return img


def _deskew(img):
    """
    Corrige inclinacao via OpenCV (Hough) ou projecao horizontal.
    Retorna a imagem rotacionada, ou a original se nao conseguir estimar.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        if img.mode != "L":
            img_l = img.convert("L")
        else:
            img_l = img

        arr = np.array(img_l)
        # Binariza temporariamente para deteccao de bordas
        _, bw = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        # Coordenadas dos pixels de texto
        coords = np.column_stack(np.where(bw > 0))
        if len(coords) < 50:
            return img

        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        # OpenCV retorna angulos no intervalo (-90, 0]
        if angle < -45:
            angle = 90 + angle
        # So corrige se o angulo for relevante (>0.5 grau) e moderado (<15)
        if abs(angle) < 0.5 or abs(angle) > 15:
            return img

        h, w = arr.shape
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            arr, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return Image.fromarray(rotated, mode="L")
    except Exception:
        return img


# ========================================================
#   OCR adaptativo
# ========================================================

def _hash_pagina(doc, pagina_idx: int) -> str:
    """Hash do conteudo binario da pagina, para cache granular."""
    try:
        page = doc[pagina_idx]
        # MediaBox + content stream da pagina (suficiente para diferenciar conteudo)
        s = f"{page.rect}_{page.get_text('rawdict').get('blocks', [])}"
        return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()[:16]
    except Exception:
        return f"idx{pagina_idx}"


def _dpi_para_pagina(page) -> int:
    rect = page.rect
    max_dim = max(rect.width, rect.height)
    if max_dim > 1200:
        return 200
    if max_dim > 800:
        return 250
    return 300


def _ocr_com_config(img_pre, psm: int, oem: int = 1) -> str:
    """Roda Tesseract com config especifica."""
    try:
        import pytesseract
        config = (
            f"--oem {oem} --psm {psm} "
            f"-c preserve_interword_spaces=1 -c user_defined_dpi=300"
        )
        return pytesseract.image_to_string(img_pre, lang="por", config=config)
    except Exception:
        return ""


def _qualidade_ocr(texto: str) -> float:
    """
    Mede qualidade do texto OCRizado:
      razao de chars validos - penalizacao de chars corrompidos +
      bonus por palavras reais.
    """
    if not texto or not texto.strip():
        return 0.0
    t = texto.strip()
    rcv = _razao_chars_validos(t)
    cor = _densidade_corrupcao(t)
    pal = sum(1 for p in t.split() if len(p) >= 3)
    return rcv - cor * 5 + min(pal / 200.0, 1.0)


def _ocr_pagina_adaptativo(
    doc,
    pagina_idx: int,
    page_hash: str,
    verbose: bool = False,
) -> tuple[str, dict]:
    """
    OCR adaptativo: tenta Otsu+PSM3, depois PSM6, depois PSM4.
    Retorna (melhor_texto, info).
    """
    try:
        from PIL import Image
    except ImportError:
        return "", {"ok": False, "motivo": "PIL ausente"}

    try:
        page = doc[pagina_idx]
        dpi = _dpi_para_pagina(page)
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
    except Exception as e:
        return "", {"ok": False, "motivo": f"render: {e}"}

    # Deskew antes da binarizacao
    img_d = _deskew(img)
    img_pre = _aplicar_otsu(img_d)

    melhor_texto = ""
    melhor_qual = 0.0
    melhor_psm = 0
    tentativas = []

    for psm in (3, 6, 4):
        chave = f"{page_hash}_dpi{dpi}_psm{psm}"
        if chave in _CACHE_OCR_PAGINA:
            texto = _CACHE_OCR_PAGINA[chave]
        else:
            texto = _ocr_com_config(img_pre, psm=psm, oem=1)
            _cache_ocr_set(chave, texto)
        qual = _qualidade_ocr(texto)
        tentativas.append({"psm": psm, "qualidade": round(qual, 3), "chars": len(texto)})
        if qual > melhor_qual:
            melhor_qual = qual
            melhor_texto = texto
            melhor_psm = psm
        # Atalho: qualidade ja boa, nao precisa testar os proximos
        if qual >= 0.85:
            break

    if verbose:
        print(f"      p.{pagina_idx + 1}: OCR adaptativo psm={melhor_psm} qual={melhor_qual:.2f}")

    return melhor_texto, {
        "ok": True,
        "dpi": dpi,
        "psm_escolhido": melhor_psm,
        "qualidade": round(melhor_qual, 3),
        "tentativas": tentativas,
    }


def _texto_melhor(a: str, b: str) -> str:
    a = (a or "").strip()
    b = (b or "").strip()
    if not a:
        return b
    if not b:
        return a
    qa = _qualidade_ocr(a) + min(len(a) / 1000.0, 5.0)
    qb = _qualidade_ocr(b) + min(len(b) / 1000.0, 5.0)
    return a if qa >= qb else b


# ========================================================
#   Detector de capa do PJe (resiliente, score probabilistico)
# ========================================================

# Sinais ponderados — score >= 4 = capa; 2-3 = zona cinza; < 2 = nao-capa
SINAIS_CAPA = [
    (re.compile(r"PJe\s*[-–]\s*Processo Judicial", re.I), 3),
    (re.compile(r"[ÓO]rg[ãa]o\s+julgador:", re.I), 2),
    (re.compile(r"\bClasse:\s*\w", re.I), 2),
    (re.compile(r"\bAssuntos?:\s*\w", re.I), 1),
    (re.compile(r"\bValor\s+da\s+causa:", re.I), 2),
    (re.compile(r"(?:Última|Ultima)\s+distribui[çc][ãa]o", re.I), 2),
    (re.compile(r"\bPartes?\b.{0,100}\b(?:Procurador|Advogado)\b", re.I | re.S), 1),
    (re.compile(r"\bDocumentos?\b[\s\S]{0,200}\bTipo\b", re.I), 2),
    (re.compile(r"\bN[úu]mero do processo:", re.I), 1),
]

CAPA_SCORE_CONFIRMADA = 5
CAPA_SCORE_ZONA_CINZA = 3
HEURISTICAS_CAPA_VERSAO = "v1"


def _score_capa(texto: str) -> tuple[int, list[str]]:
    """Retorna (score, sinais_acionados) do texto contra heuristicas de capa."""
    if not texto:
        return 0, []
    score = 0
    hits = []
    for padrao, peso in SINAIS_CAPA:
        if padrao.search(texto):
            score += peso
            hits.append(padrao.pattern[:40])
    return score, hits


def _eh_capa_pje(texto: str) -> tuple[bool, bool, int]:
    """
    Retorna (eh_capa, zona_cinza, score).
    eh_capa: True quando score >= CAPA_SCORE_CONFIRMADA.
    zona_cinza: True quando CAPA_SCORE_ZONA_CINZA <= score < CAPA_SCORE_CONFIRMADA.
    """
    score, _ = _score_capa(texto)
    return score >= CAPA_SCORE_CONFIRMADA, CAPA_SCORE_ZONA_CINZA <= score < CAPA_SCORE_CONFIRMADA, score


def _extrair_meta_capa(texto: str) -> dict:
    """Extrai metadados estruturados da capa."""
    meta = {
        "classe": "", "assunto": "", "orgao": "",
        "valor": "", "distribuicao": "",
        "exequente": "", "executado": "",
    }
    if not texto:
        return meta

    def grab(pat):
        m = re.search(pat, texto, re.I)
        return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    meta["classe"] = grab(r"Classe:\s*\*?\*?([^\n*]+)")
    meta["assunto"] = grab(r"Assuntos?:\s*\*?\*?([^\n*]+)")
    meta["orgao"] = grab(r"[ÓO]rg[ãa]o\s+julgador:\s*([^\n*]+)")
    meta["valor"] = grab(r"Valor\s+da\s+causa:\s*R?\$?\s*([^\n*]+)")
    meta["distribuicao"] = grab(r"(?:Última|Ultima)\s+distribui[çc][ãa]o\s*:\s*([^\n*]+)")

    exq = re.search(
        r"([A-ZÁ-Ú][A-ZÁ-Ú\s.\-&]{2,80}?)\s*\((?:EXEQUENTE|REQUERENTE|AUTOR|RECLAMANTE|IMPETRANTE)\)",
        texto,
    )
    exc = re.search(
        r"([A-ZÁ-Ú][A-ZÁ-Ú\s.\-&]{2,80}?)\s*\((?:EXECUTADO|REQUERIDO|R[ÉE]U|RECLAMADO|IMPETRADO)\)",
        texto,
    )
    if exq:
        meta["exequente"] = re.sub(r"\s+", " ", exq.group(1)).strip()
    if exc:
        meta["executado"] = re.sub(r"\s+", " ", exc.group(1)).strip()
    return meta


def _fallback_metadados_pdf(doc) -> dict:
    """Tenta extrair classe/assunto dos metadados PDF quando capa nao bate score."""
    try:
        info = doc.metadata or {}
    except Exception:
        return {}
    titulo = (info.get("title") or "").strip()
    assunto = (info.get("subject") or "").strip()
    out = {}
    if titulo:
        out["classe"] = titulo[:100]
    if assunto:
        out["assunto"] = assunto[:200]
    return out


def _extrair_movimentacao(texto: str) -> list[dict]:
    pat = re.compile(r"(\d{2}/\d{2}/\d{4})\s{1,10}([^\n]{10,120})", re.M)
    return [
        {"data": m.group(1), "descricao": m.group(2).strip()}
        for m in pat.finditer(texto)
    ]


# ========================================================
#   Agrupamento de pecas
# ========================================================

MAX_GAP_AGRUPAMENTO = 1   # paginas
MAX_GAP_DOC_CONTINUACAO = 1


def _datas_em(texto: str) -> list[str]:
    return re.findall(r"\b\d{2}/\d{2}/\d{4}\b", texto[:1500])


def _deve_agrupar(ultimo: dict, atual: dict) -> bool:
    """
    Regras de agrupamento (na ordem):
      1. doc_id e separador forte: se ambos tem doc_id explicito e sao distintos -> nao agrupa.
      2. Datas distintas em peca de mesmo tipo -> nao agrupa.
      3. Gap entre paginas > MAX_GAP_AGRUPAMENTO -> nao agrupa.
      4. Mesmo tipo + paginas continuas -> agrupa.
      5. DOC apos peca COMPLETA + mesmo doc_id ou sem doc_id + adjacente -> continuacao.
    """
    gap = atual["pag"] - ultimo["pag_fim"]
    if gap > MAX_GAP_AGRUPAMENTO:
        return False

    # doc_id como separador forte
    doc_ids_ultimo = [d[0] for d in ultimo.get("doc_ids", []) if d]
    doc_id_atual = atual.get("doc_id")
    if doc_ids_ultimo and doc_id_atual:
        if doc_id_atual[0] not in doc_ids_ultimo:
            return False

    if ultimo["tipo"] == atual["tipo"]:
        # Penaliza datas distintas em mesmo tipo
        datas_u = set(_datas_em(ultimo["texto"]))
        datas_a = set(_datas_em(atual["texto"]))
        if datas_u and datas_a and not (datas_u & datas_a):
            # Conjuntos de datas disjuntos: provavelmente pecas distintas
            return False
        return True

    # DOC apos peca COMPLETA -> continuacao se adjacente
    if atual["tipo"] == "DOC" and ultimo["tipo"] in PECAS_COMPLETAS:
        if gap <= MAX_GAP_DOC_CONTINUACAO:
            return True

    return False


# ========================================================
#   Geracao do markdown
# ========================================================

def _bloco_cabecalho(numero: str, meta: dict, n_paginas: int, n_pecas: int) -> list[str]:
    blocos = [f"# {numero}", ""]
    linhas = []
    if meta.get("classe"):
        linhas.append(f"**Classe:** {meta['classe']}")
    if meta.get("assunto"):
        linhas.append(f"**Assunto:** {meta['assunto']}")
    if meta.get("orgao"):
        linhas.append(f"**Órgão julgador:** {meta['orgao']}")
    if meta.get("valor"):
        linhas.append(f"**Valor da causa:** R$ {meta['valor']}")
    if meta.get("distribuicao"):
        linhas.append(f"**Distribuição:** {meta['distribuicao']}")
    if meta.get("exequente"):
        linhas.append(f"**Autor/Exequente:** {meta['exequente']}")
    if meta.get("executado"):
        linhas.append(f"**Réu/Executado:** {meta['executado']}")
    linhas.append(f"**Total de páginas:** {n_paginas}")
    linhas.append(f"**Peças identificadas:** {n_pecas}")

    if linhas:
        blocos.append("  \n".join(linhas))
        blocos.append("")
    blocos.extend(["---", ""])
    return blocos


def _bloco_movimentacao(mov: list[dict]) -> list[str]:
    if not mov:
        return []
    linhas = ["## MOVIMENTAÇÃO PROCESSUAL", "", "| Data | Descrição |", "|------|-----------|"]
    for m in mov:
        linhas.append(f"| {m['data']} | {m['descricao']} |")
    linhas.append("")
    return linhas


def _bloco_sinalizadores(sin: dict) -> list[str]:
    linhas = [
        "## SINALIZADORES PROCESSUAIS (extração automática)",
        "",
        f"- **Fase aparente**: {sin['fase_aparente']}",
        f"- **Provável status da cautelar**: {sin['provavel_status_cautelar']}",
    ]
    eventos = sin["eventos"]
    flags = [
        ("Audiência de custódia", eventos.get("tem_audiencia_custodia")),
        ("Liberdade provisória", eventos.get("tem_liberdade_provisoria")),
        ("Cautelar Art. 319", eventos.get("tem_cautelar_319")),
        ("Termo de compromisso", eventos.get("tem_termo_compromisso")),
        ("Sursis processual", eventos.get("tem_sursis_processual")),
        ("ANPP", eventos.get("tem_anpp")),
        ("Transação penal", eventos.get("tem_transacao_penal")),
        ("Revogação de cautelar", eventos.get("tem_revogacao")),
        ("Preventiva decretada", eventos.get("tem_preventiva_decretada")),
        ("Sentença", eventos.get("tem_sentenca")),
        ("Trânsito em julgado", eventos.get("tem_transito_julgado")),
        ("Extinção da punibilidade", eventos.get("tem_extincao_punibilidade")),
    ]
    ativas = [n for n, v in flags if v]
    if ativas:
        linhas.append(f"- **Eventos detectados**: {', '.join(ativas)}")

    if eventos.get("eventos"):
        linhas.append("- **Linha do tempo**:")
        for ev in eventos["eventos"]:
            ids = formatar_doc_ids(ev.get("doc_ids", []))
            ids_str = f" [{ids}]" if ids else ""
            data = f" em {ev['data_detectada']}" if ev.get("data_detectada") else ""
            linhas.append(f"  - {ev['tipo']} (p.{ev['pagina']}{ids_str}){data}")
    linhas.append("")
    return linhas


def _bloco_dados_pessoais(dados: dict) -> list[str]:
    linhas = ["## DADOS PESSOAIS DETECTADOS (extração automática)", ""]
    if dados.get("cpfs"):
        linhas.append(f"- **CPFs**: {', '.join(dados['cpfs'][:10])}")
    if dados.get("rgs"):
        linhas.append(f"- **RGs**: {', '.join(dados['rgs'][:5])}")
    if dados.get("telefones"):
        linhas.append(f"- **Telefones**: {', '.join(dados['telefones'][:5])}")
    if dados.get("ceps"):
        linhas.append(f"- **CEPs**: {', '.join(dados['ceps'][:5])}")
    if dados.get("datas"):
        linhas.append(f"- **Datas**: {', '.join(dados['datas'][:10])}")
    if len(linhas) == 2:
        return []
    linhas.append("")
    linhas.append("> Verificar papel processual (réu/vítima/testemunha) antes de cadastrar.")
    linhas.append("")
    return linhas


def _bloco_pecas(grupos: list[dict]) -> list[str]:
    linhas: list[str] = []
    resumos: list[str] = []

    for g in grupos:
        pags = (
            f"p.{g['pag_ini']}"
            if g["pag_ini"] == g["pag_fim"]
            else f"p.{g['pag_ini']}-{g['pag_fim']}"
        )
        ids = formatar_doc_ids(g["doc_ids"])
        ids_str = f" — {ids}" if ids else ""
        conf = g.get("confianca", 1.0)

        if g["tipo"] in PECAS_COMPLETAS:
            cab = f"## {g['tipo']} ({pags}){ids_str}"
            if conf < 0.5:
                cab += f"  <!-- confiança: {conf:.0%} -->"
            linhas.extend([cab, "", g["texto"], ""])

        elif g["tipo"] in PECAS_RESUMO:
            entry = f"- **{g['tipo']}** {pags}"
            if ids:
                entry += f" [{ids}]"
            entry += f": {primeira_linha(g['texto'])}"
            resumos.append(entry)

    if resumos:
        linhas.append("## Peças Secundárias")
        linhas.append("")
        linhas.extend(resumos)
        linhas.append("")

    return linhas


def _gerar_markdown(
    numero: str,
    meta: dict,
    n_paginas: int,
    grupos: list[dict],
    sinalizadores: dict,
    dados_pessoais: dict,
    movimentacao: list[dict],
) -> str:
    n_pecas_completas = sum(1 for g in grupos if g["tipo"] in PECAS_COMPLETAS)
    n_resumos = sum(1 for g in grupos if g["tipo"] in PECAS_RESUMO)

    blocos = (
        _bloco_cabecalho(numero, meta, n_paginas, n_pecas_completas + n_resumos)
        + _bloco_movimentacao(movimentacao)
        + _bloco_sinalizadores(sinalizadores)
        + _bloco_dados_pessoais(dados_pessoais)
        + _bloco_pecas(grupos)
    )
    return "\n".join(blocos).strip() + "\n"


# ========================================================
#   Continuacao de pecas (mesmo doc_id + tipo + contiguidade)
# ========================================================

def _e_continuacao(ant: dict, atual: dict) -> bool:
    """Mesmo doc_id + mesmo tipo + paginas contiguas -> continuacao."""
    if ant["tipo"] != atual["tipo"]:
        return False
    if atual["pag"] - ant["pag_fim"] > 1:
        return False
    ant_ids = {d[0] for d in ant.get("doc_ids", []) if d}
    if atual.get("doc_id") and atual["doc_id"][0] in ant_ids:
        return True
    return False


# ========================================================
#   Pipeline principal
# ========================================================

def _extrair_chunks_com_retry(pdf_path: str, max_tentativas: int = 2):
    import pymupdf4llm

    erro = None
    for tentativa in range(max_tentativas):
        try:
            return pymupdf4llm.to_markdown(pdf_path, page_chunks=True)
        except Exception as e:
            erro = e
            if tentativa == 0:
                try:
                    pymupdf4llm.use_layout(False)
                except Exception:
                    pass
            time.sleep(0.5)
    raise erro


def _md_hash(texto: str) -> str:
    return hashlib.md5(texto.encode("utf-8", errors="ignore")).hexdigest()


def processar_pdf(pdf_path: str, dir_saida: str, opts: dict | None = None) -> dict:
    """
    Processa um unico PDF. Funcao isolavel para uso em ProcessPoolExecutor.

    opts: {use_ocr, force_ocr, ocr_threshold, verbose, debug, skip_se_md_igual}
    Retorna dict (compativo com codigo existente) — internamente usa ResultadoExtracao.
    """
    opts = opts or {}
    use_ocr = opts.get("use_ocr", True)
    force_ocr = opts.get("force_ocr", False)
    threshold = opts.get("ocr_threshold", DEFAULT_OCR_THRESHOLD)
    verbose = opts.get("verbose", False)
    debug = opts.get("debug", False)
    skip_se_md_igual = opts.get("skip_se_md_igual", True)

    pdf_path = str(pdf_path)
    dir_saida = Path(dir_saida)
    dir_saida.mkdir(parents=True, exist_ok=True)

    nome = Path(pdf_path).name
    numero = extrair_numero_processo(nome)
    t0 = time.time()

    # Abre o PDF UMA VEZ e mantem aberto durante todo o processamento
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
    except Exception as e:
        return ResultadoExtracao(
            numero=numero, arquivo=nome, status="ERRO",
            erro=f"abrir pdf: {e}",
        ).to_dict()

    n_paginas = len(doc)

    try:
        chunks = _extrair_chunks_com_retry(pdf_path)
    except Exception as e:
        doc.close()
        return ResultadoExtracao(
            numero=numero, arquivo=nome, status="ERRO",
            erro=f"extrair: {e}",
        ).to_dict()

    chars_bruto = sum(len(c.get("text", "")) for c in chunks)
    texto_capa = chunks[0].get("text", "") if chunks else ""

    eh_capa, zona_cinza, score_capa = _eh_capa_pje(texto_capa)
    meta = _extrair_meta_capa(texto_capa) if (eh_capa or zona_cinza) else {}
    movimentacao = _extrair_movimentacao(texto_capa) if (eh_capa or zona_cinza) else []

    # Fallback de metadados: usa info do PDF se capa nao confirmou e classe/assunto faltam
    if (not eh_capa) and not (meta.get("classe") or meta.get("assunto")):
        meta.update(_fallback_metadados_pdf(doc))

    # Processar paginas
    pecas: list[dict] = []
    paginas_ocr = 0
    debug_paginas: list[dict] = []
    pag_classificacoes: list[dict] = []
    debug_limpeza_global: list[dict] = []

    for i, chunk in enumerate(chunks):
        if i == 0 and eh_capa:
            continue  # descarta lixo da capa (texto-base; metadados ja capturados)

        texto_raw = chunk.get("text", "")

        if use_ocr:
            page_hash = _hash_pagina(doc, i)
            faz_ocr = force_ocr
            motivo_ocr = "forcado" if force_ocr else ""
            if not force_ocr:
                precisa, motivo_ocr = deve_ocrizar(texto_raw, threshold)
                faz_ocr = precisa

            if faz_ocr:
                texto_ocr, info_ocr = _ocr_pagina_adaptativo(doc, i, page_hash, verbose=verbose)
                if texto_ocr:
                    antes = len(texto_raw)
                    texto_raw = _texto_melhor(texto_raw, texto_ocr)
                    if len(texto_raw) > antes:
                        paginas_ocr += 1
                        if verbose:
                            print(f"      p.{i+1}: OCR ({motivo_ocr}, +{len(texto_raw) - antes} chars)")
                if debug:
                    debug_paginas.append({"pagina": i + 1, "motivo": motivo_ocr, "info": info_ocr})

        doc_id = extrair_doc_id(texto_raw)

        debug_limpeza_pag: list[dict] = []
        texto_limpo = limpar_texto(
            texto_raw,
            verbose=debug,
            debug_log=debug_limpeza_pag if debug else None,
        )
        if debug and debug_limpeza_pag:
            debug_limpeza_global.append({"pagina": i + 1, "remocoes": debug_limpeza_pag[:30]})

        if len(texto_limpo) < 30:
            continue

        tipo, score, confianca = classificar_peca_com_score(texto_limpo)

        if debug:
            pag_classificacoes.append({
                "pagina": i + 1,
                "tipo": tipo,
                "score": score,
                "confianca": confianca,
            })

        # Confianca muito baixa em peca completa -> rebaixa para DOC
        if confianca < 0.3 and tipo in PECAS_COMPLETAS:
            tipo = "DOC"

        if tipo in PECAS_DESCARTE:
            continue

        pecas.append({
            "pag": i + 1,
            "tipo": tipo,
            "texto": texto_limpo,
            "doc_id": doc_id,
            "confianca": confianca,
        })

    # Agrupamento + continuacao
    grupos: list[dict] = []
    debug_agrupamento: list[dict] = []
    for p in pecas:
        if grupos:
            ultimo = grupos[-1]
            if _e_continuacao(ultimo, p):
                ultimo["pag_fim"] = p["pag"]
                ultimo["texto"] += "\n\n" + p["texto"]
                ultimo["confianca"] = min(ultimo["confianca"], p["confianca"])
                if p["doc_id"] and p["doc_id"] not in ultimo["doc_ids"]:
                    ultimo["doc_ids"].append(p["doc_id"])
                if debug:
                    debug_agrupamento.append({
                        "acao": "continuacao",
                        "tipo": p["tipo"],
                        "pag": p["pag"],
                    })
                continue
            if _deve_agrupar(ultimo, p):
                ultimo["pag_fim"] = p["pag"]
                ultimo["texto"] += "\n\n" + p["texto"]
                ultimo["confianca"] = min(ultimo["confianca"], p["confianca"])
                if p["doc_id"] and p["doc_id"] not in ultimo["doc_ids"]:
                    ultimo["doc_ids"].append(p["doc_id"])
                if debug:
                    debug_agrupamento.append({
                        "acao": "agrupar",
                        "tipo_ant": ultimo["tipo"],
                        "tipo_atual": p["tipo"],
                        "pag": p["pag"],
                    })
                continue

        grupos.append({
            "tipo": p["tipo"],
            "pag_ini": p["pag"],
            "pag_fim": p["pag"],
            "texto": p["texto"],
            "doc_ids": [p["doc_id"]] if p["doc_id"] else [],
            "confianca": p["confianca"],
        })
        if debug:
            debug_agrupamento.append({
                "acao": "novo",
                "tipo": p["tipo"],
                "pag": p["pag"],
            })

    sinalizadores = detectar_sinalizadores_processuais(grupos)
    texto_total = "\n".join(g["texto"] for g in grupos)
    dados_pessoais = detectar_dados_pessoais(texto_total)

    md_text = _gerar_markdown(
        numero, meta, n_paginas, grupos,
        sinalizadores, dados_pessoais, movimentacao,
    )

    nome_saida = numero.replace(".", "_").replace("-", "_") + ".md"
    saida_path = dir_saida / nome_saida

    md_hash_atual = _md_hash(md_text)
    md_hash_anterior = ""
    if saida_path.exists() and skip_se_md_igual:
        try:
            md_hash_anterior = _md_hash(saida_path.read_text(encoding="utf-8"))
        except Exception:
            md_hash_anterior = ""

    if md_hash_atual != md_hash_anterior:
        saida_path.write_text(md_text, encoding="utf-8")

    # Metricas (observabilidade)
    metricas = {
        "paginas_total": n_paginas,
        "paginas_ocr": paginas_ocr,
        "taxa_ocr": round(paginas_ocr / n_paginas, 3) if n_paginas else 0.0,
        "score_capa": score_capa,
        "capa_zona_cinza": zona_cinza,
        "heuristicas_capa_versao": HEURISTICAS_CAPA_VERSAO,
        "n_grupos": len(grupos),
        "n_pecas_completas": sum(1 for g in grupos if g["tipo"] in PECAS_COMPLETAS),
        "n_pecas_resumo": sum(1 for g in grupos if g["tipo"] in PECAS_RESUMO),
        "n_doc_orfaos": sum(1 for g in grupos if g["tipo"] == "DOC"),
        "tempo_s": round(time.time() - t0, 2),
        "md_reescrito": md_hash_atual != md_hash_anterior,
        "confianca_distribuicao": {
            "alta": sum(1 for g in grupos if g["confianca"] >= 0.7),
            "media": sum(1 for g in grupos if 0.4 <= g["confianca"] < 0.7),
            "baixa": sum(1 for g in grupos if g["confianca"] < 0.4),
        },
    }

    log_path = dir_saida / nome_saida.replace(".md", ".log.json")
    log_data = {
        "arquivo": nome,
        "timestamp": datetime.now().isoformat(),
        **metricas,
        "pecas": [
            {
                "tipo": g["tipo"],
                "paginas": f"{g['pag_ini']}-{g['pag_fim']}",
                "confianca": round(g["confianca"], 2),
            }
            for g in grupos
        ],
        "movimentacao_itens": len(movimentacao),
    }
    if debug:
        debug_dir = dir_saida / "_debug"
        debug_dir.mkdir(exist_ok=True)
        salvar_json(debug_dir / nome_saida.replace(".md", ".debug.json"), {
            "ocr_paginas": debug_paginas,
            "classificacoes": pag_classificacoes,
            "agrupamento": debug_agrupamento,
            "limpeza_amostra": debug_limpeza_global[:20],
        })
    salvar_json(log_path, log_data)

    doc.close()

    resultado = ResultadoExtracao(
        numero=numero,
        arquivo=nome,
        status="OK",
        arquivo_saida=nome_saida,
        total_paginas=n_paginas,
        paginas_ocr=paginas_ocr,
        classe=meta.get("classe", ""),
        assunto=meta.get("assunto", ""),
        pecas=sum(1 for g in grupos if g["tipo"] in PECAS_COMPLETAS or g["tipo"] in PECAS_RESUMO),
        chars_bruto=chars_bruto,
        chars_limpo=len(md_text),
        tokens_aprox=len(md_text) // 4,
        reducao_pct=(1 - len(md_text) / chars_bruto) * 100 if chars_bruto else 0,
        cache_key=cache_key_arquivo(pdf_path),
        fase_aparente=sinalizadores["fase_aparente"],
        provavel_status_cautelar=sinalizadores["provavel_status_cautelar"],
        metricas=metricas,
    )
    return resultado.to_dict()
