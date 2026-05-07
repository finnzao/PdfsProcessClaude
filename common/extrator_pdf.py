"""
common/extrator_pdf.py — Pipeline de extracao PDF -> markdown otimizado.

Melhorias sobre a versao original:
  - Detecta encoding corrompido (texto-lixo) alem de pagina-vazia
  - OCR comparativo: tenta OCR e usa se for melhor que o nativo
  - Pre-processamento Otsu antes do OCR (binarizacao)
  - DPI adaptativo baseado no tamanho da pagina
  - Detecta capa do PJe e descarta o lixo da tabela de documentos
  - Mescla DOCs orfaos na peca completa anterior
  - Logs detalhados opcionais
  - Retry em falhas transitorias do PyMuPDF
"""

from __future__ import annotations

import hashlib
import inspect
import io
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

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
#   Constantes
# ========================================================
DEFAULT_OCR_THRESHOLD = 80          # chars/pag abaixo do qual aciona OCR
MIN_RAZAO_VALIDOS = 0.55            # razao de chars validos para aceitar texto nativo
MAX_DENSIDADE_CORRUPCAO = 0.02      # acima disto, encoding esta podre

# Caracteres tipicos de encoding corrompido em PDFs juridicos brasileiros
# (fonte mal-mapeada, Identity-H sem CMap, MacRoman travestido)
CHARS_CORROMPIDOS = re.compile(r"[∞ÈÁ„‡ïÙ˙ıÌı‰ÒÏü¿¬«¶®©ª¯±²³µ¸¹º»¼½¾]")
RE_CHARS_VALIDOS = re.compile(
    r"[a-zA-ZáéíóúâêôãõàèìòùäëïöüçñÁÉÍÓÚÂÊÔÃÕÀÈÌÒÙÄËÏÖÜÇÑ0-9 ]"
)


# ========================================================
#   Cache e versionamento
# ========================================================

def _md5_arquivo(path: str | Path) -> str:
    """MD5 incremental do conteudo do arquivo."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(8192), b""):
            h.update(bloco)
    return h.hexdigest()


def versao_utils() -> str:
    """
    Hash dos modulos que afetam a saida. Quando qualquer um muda,
    o cache invalida automaticamente.
    """
    from common import (
        classificador_pecas,
        limpeza_pje,
        sinalizadores_proc,
    )
    h = hashlib.md5()
    for mod in (classificador_pecas, limpeza_pje, sinalizadores_proc):
        h.update(inspect.getsource(mod).encode())
    return h.hexdigest()[:8]


def cache_key_arquivo(pdf_path: str | Path) -> str:
    """Chave composta: md5(pdf) + versao(utils). Invalida se qualquer mudar."""
    return f"{_md5_arquivo(pdf_path)}_{versao_utils()}"


# ========================================================
#   Heuristicas de necessidade de OCR
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
    """
    Decide se vale a pena fazer OCR. Retorna (precisa, motivo).

    Criterios em ordem:
      a) texto curto demais
      b) texto presente mas com encoding corrompido
      c) razao de chars validos baixa (texto-lixo)
      d) poucas palavras de 3+ letras (fragmentado demais)
    """
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
#   OCR com pre-processamento Otsu
# ========================================================

def _aplicar_otsu(img):
    """Binarizacao Otsu para melhorar OCR de documentos escaneados."""
    try:
        import numpy as np
        from PIL import Image, ImageOps

        if img.mode != "L":
            img = img.convert("L")

        arr = np.array(img)

        # Histograma
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

        # Aplica com pequeno bias: Tesseract gosta de texto "gordo"
        thr_adj = min(255, threshold + 10)
        binarizada = (arr >= thr_adj).astype(np.uint8) * 255
        return Image.fromarray(binarizada, mode="L")
    except Exception:
        # Sem numpy ou falhou: devolve original
        return img


def _ocr_pagina(pdf_path: str, pagina_idx: int) -> str:
    """OCR de uma pagina especifica com pre-processamento."""
    try:
        import pymupdf
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""

    try:
        doc = pymupdf.open(pdf_path)
        page = doc[pagina_idx]

        # DPI adaptativo: paginas grandes recebem DPI menor para nao explodir mem
        rect = page.rect
        max_dim = max(rect.width, rect.height)
        if max_dim > 1200:
            dpi = 200
        elif max_dim > 800:
            dpi = 250
        else:
            dpi = 300

        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        img_pre = _aplicar_otsu(img)

        texto = pytesseract.image_to_string(
            img_pre,
            lang="por",
            config="--psm 3 -c preserve_interword_spaces=1 -c user_defined_dpi=300",
        )
        doc.close()
        return texto
    except Exception:
        return ""


def _texto_melhor(a: str, b: str) -> str:
    """Compara dois textos extraidos e devolve o melhor."""
    a = (a or "").strip()
    b = (b or "").strip()

    if not a:
        return b
    if not b:
        return a

    # Heuristica composta: tamanho + qualidade do encoding
    ra = _razao_chars_validos(a) - _densidade_corrupcao(a) * 5
    rb = _razao_chars_validos(b) - _densidade_corrupcao(b) * 5

    # Bonus por tamanho (mas cap)
    score_a = ra * 100 + min(len(a) / 1000, 5)
    score_b = rb * 100 + min(len(b) / 1000, 5)

    return a if score_a >= score_b else b


# ========================================================
#   Detector de capa do PJe
# ========================================================

def _eh_capa_pje(texto: str) -> bool:
    """Heuristica: capa do PJe tem metadados + tabela 'Documentos' que vira lixo."""
    if not texto:
        return False
    sinais = [
        r"PJe\s*[-–]\s*Processo Judicial",
        r"[ÓO]rg[ãa]o\s+julgador:",
        r"Classe:\s*\w",
        r"Valor\s+da\s+causa:",
    ]
    hits = sum(1 for p in sinais if re.search(p, texto, re.I))
    tem_tabela_docs = bool(re.search(r"\bDocumentos?\b[\s\S]{0,200}\bTipo\b", texto, re.I))
    return hits >= 3 and tem_tabela_docs


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

    # Partes
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


def _extrair_movimentacao(texto: str) -> list[dict]:
    """Linhas de movimentacao processual."""
    pat = re.compile(r"(\d{2}/\d{2}/\d{4})\s{1,10}([^\n]{10,120})", re.M)
    return [
        {"data": m.group(1), "descricao": m.group(2).strip()}
        for m in pat.finditer(texto)
    ]


# ========================================================
#   Agrupamento de pecas
# ========================================================

def _deve_agrupar(ultimo: dict, atual: dict) -> bool:
    """Decide se duas pecas adjacentes devem virar uma unica."""
    # Mesmo tipo + paginas continuas
    if ultimo["tipo"] == atual["tipo"]:
        if atual["pag"] - ultimo["pag_fim"] <= 1:
            # Se ambas tem doc_id explicito e diferentes → pecas distintas
            if ultimo["doc_ids"] and atual["doc_id"]:
                return atual["doc_id"][0] in [d[0] for d in ultimo["doc_ids"]]
            return True
        return False

    # DOC apos peca COMPLETA → continuacao natural
    if atual["tipo"] == "DOC" and ultimo["tipo"] in PECAS_COMPLETAS:
        if atual["pag"] - ultimo["pag_fim"] <= 1:
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
        # DOC orfaos sao filtrados aqui — nao poluem o markdown

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
#   Pipeline principal de um PDF
# ========================================================

def _extrair_chunks_com_retry(pdf_path: str, max_tentativas: int = 2):
    """Extrai chunks com retry. PyMuPDF as vezes falha em PDFs corrompidos."""
    import pymupdf4llm

    erro = None
    for tentativa in range(max_tentativas):
        try:
            return pymupdf4llm.to_markdown(pdf_path, page_chunks=True)
        except Exception as e:
            erro = e
            if tentativa == 0:
                # Tenta sem layout
                try:
                    pymupdf4llm.use_layout(False)
                except Exception:
                    pass
            time.sleep(0.5)
    raise erro


def processar_pdf(pdf_path: str, dir_saida: str, opts: dict | None = None) -> dict:
    """
    Processa um unico PDF. Funcao isolavel para uso em ProcessPoolExecutor.

    opts: {use_ocr, force_ocr, ocr_threshold, verbose}
    """
    opts = opts or {}
    use_ocr = opts.get("use_ocr", True)
    force_ocr = opts.get("force_ocr", False)
    threshold = opts.get("ocr_threshold", DEFAULT_OCR_THRESHOLD)
    verbose = opts.get("verbose", False)

    pdf_path = str(pdf_path)
    dir_saida = Path(dir_saida)
    dir_saida.mkdir(parents=True, exist_ok=True)

    nome = Path(pdf_path).name
    numero = extrair_numero_processo(nome)
    t0 = time.time()

    # Numero de paginas
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        n_paginas = len(doc)
        doc.close()
    except Exception as e:
        return {"numero": numero, "arquivo": nome, "status": "ERRO", "erro": f"abrir pdf: {e}"}

    # Extracao base
    try:
        chunks = _extrair_chunks_com_retry(pdf_path)
    except Exception as e:
        return {"numero": numero, "arquivo": nome, "status": "ERRO", "erro": f"extrair: {e}"}

    chars_bruto = sum(len(c.get("text", "")) for c in chunks)
    texto_capa = chunks[0].get("text", "") if chunks else ""
    eh_capa = _eh_capa_pje(texto_capa)
    meta = _extrair_meta_capa(texto_capa) if eh_capa else {}
    movimentacao = _extrair_movimentacao(texto_capa) if eh_capa else []

    # Processar pagina por pagina
    pecas: list[dict] = []
    paginas_ocr = 0
    for i, chunk in enumerate(chunks):
        # Capa do PJe: descarta texto bruto (metadados ja extraidos)
        if i == 0 and eh_capa:
            continue

        texto_raw = chunk.get("text", "")

        # OCR condicional
        if use_ocr:
            if force_ocr:
                texto_ocr = _ocr_pagina(pdf_path, i)
                if texto_ocr:
                    texto_raw = _texto_melhor(texto_raw, texto_ocr)
                    paginas_ocr += 1
                    if verbose:
                        print(f"      p.{i+1}: OCR forcado")
            else:
                precisa, motivo = deve_ocrizar(texto_raw, threshold)
                if precisa:
                    texto_ocr = _ocr_pagina(pdf_path, i)
                    if texto_ocr:
                        antes = len(texto_raw)
                        texto_raw = _texto_melhor(texto_raw, texto_ocr)
                        if len(texto_raw) > antes:
                            paginas_ocr += 1
                            if verbose:
                                print(f"      p.{i+1}: OCR ({motivo}, +{len(texto_raw) - antes} chars)")

        doc_id = extrair_doc_id(texto_raw)
        texto_limpo = limpar_texto(texto_raw)
        if len(texto_limpo) < 30:
            continue

        tipo, score = classificar_peca_com_score(texto_limpo)
        confianca = min(score / 20, 1.0) if score > 0 else 0.3

        # Confianca muito baixa em peca completa → rebaixa para DOC
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

    # Agrupamento
    grupos: list[dict] = []
    for p in pecas:
        if grupos and _deve_agrupar(grupos[-1], p):
            grupos[-1]["pag_fim"] = p["pag"]
            grupos[-1]["texto"] += "\n\n" + p["texto"]
            grupos[-1]["confianca"] = min(grupos[-1]["confianca"], p["confianca"])
            if p["doc_id"]:
                grupos[-1]["doc_ids"].append(p["doc_id"])
        else:
            grupos.append({
                "tipo": p["tipo"],
                "pag_ini": p["pag"],
                "pag_fim": p["pag"],
                "texto": p["texto"],
                "doc_ids": [p["doc_id"]] if p["doc_id"] else [],
                "confianca": p["confianca"],
            })

    # Sinalizadores e dados
    sinalizadores = detectar_sinalizadores_processuais(grupos)
    texto_total = "\n".join(g["texto"] for g in grupos)
    dados_pessoais = detectar_dados_pessoais(texto_total)

    # Markdown
    md_text = _gerar_markdown(
        numero, meta, n_paginas, grupos,
        sinalizadores, dados_pessoais, movimentacao,
    )

    nome_saida = numero.replace(".", "_").replace("-", "_") + ".md"
    saida_path = dir_saida / nome_saida
    saida_path.write_text(md_text, encoding="utf-8")

    # Log estruturado
    log_path = dir_saida / nome_saida.replace(".md", ".log.json")
    salvar_json(log_path, {
        "arquivo": nome,
        "timestamp": datetime.now().isoformat(),
        "paginas_total": n_paginas,
        "paginas_ocr": paginas_ocr,
        "tempo_s": round(time.time() - t0, 2),
        "pecas": [
            {
                "tipo": g["tipo"],
                "paginas": f"{g['pag_ini']}-{g['pag_fim']}",
                "confianca": round(g["confianca"], 2),
            }
            for g in grupos
        ],
        "movimentacao_itens": len(movimentacao),
    })

    return {
        "numero": numero,
        "arquivo": nome,
        "arquivo_saida": nome_saida,
        "total_paginas": n_paginas,
        "paginas_ocr": paginas_ocr,
        "classe": meta.get("classe", ""),
        "assunto": meta.get("assunto", ""),
        "pecas": sum(1 for g in grupos if g["tipo"] in PECAS_COMPLETAS or g["tipo"] in PECAS_RESUMO),
        "chars_bruto": chars_bruto,
        "chars_limpo": len(md_text),
        "tokens_aprox": len(md_text) // 4,
        "reducao_pct": (1 - len(md_text) / chars_bruto) * 100 if chars_bruto else 0,
        "cache_key": cache_key_arquivo(pdf_path),
        "status": "OK",
        "fase_aparente": sinalizadores["fase_aparente"],
        "provavel_status_cautelar": sinalizadores["provavel_status_cautelar"],
    }
