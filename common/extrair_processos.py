#!/usr/bin/env python3
"""
extrair_processos.py — Extrai texto de PDFs de processos judiciais (PJe/TJBA).

Roda 1 vez. Saída compartilhada em textos_extraidos/.
Todos os services leem de lá.

USO:
    python common/extrair_processos.py
    # ou via CLI:
    python run.py extrair
"""

import os
import re
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# Paths relativos à raiz do projeto
DIR_PDFS = Path(__file__).parent.parent / "pdfs"
DIR_SAIDA = Path(__file__).parent.parent / "textos_extraidos"
RELATORIO_PATH = Path(__file__).parent.parent / "relatorio_extracao.json"
MAPEAMENTO_PATH = Path(__file__).parent.parent / "mapeamento_processos.json"

DIR_SAIDA.mkdir(exist_ok=True)

MIN_CHARS_PAGINA = 50
SCAN_CHARS_POR_AREA = 0.005
SCAN_IMG_MIN_FRAC = 0.3
SCAN_LINHAS_CURTAS_FRAC = 0.8

PECAS_COMPLETAS = {"DENUNCIA", "SENTENCA", "DECISAO", "DESPACHO", "ATA",
                   "PRONUNCIA", "ALEGACOES", "RESPOSTA", "RECURSO", "LAUDO"}
PECAS_RESUMO = {"CERTIDAO", "INTIMACAO", "OFICIO", "MANDADO", "ALVARA", "PETICAO"}

# ============================================================
# PROGRESSO
# ============================================================
class Progresso:
    def __init__(self, total):
        self.total = total
        self.atual = 0
        self.inicio = time.time()
        self.inicio_pdf = time.time()

    def novo_pdf(self, idx, nome, n_pags):
        self.atual = idx
        self.inicio_pdf = time.time()
        pct = (idx - 1) / self.total * 100
        print(f"\n[{idx}/{self.total}] ({pct:.1f}%) {nome}")
        print(f"  {n_pags} págs | ", end="", flush=True)

    def pagina(self, n, total, tipo):
        simbolos = {"txt": "#", "ocr": "O", "scan": "S", "vazia": ".", "ocr_fail": "X"}
        step = max(1, total // 30)
        if n % step == 0 or n <= 1 or n == total:
            print(simbolos.get(tipo, "?"), end="", flush=True)

    def concluido(self, r):
        t = time.time() - self.inicio_pdf
        if r["status"] == "OK":
            print(f" | {t:.1f}s")
            print(f"  → {r['tokens_aprox']:,} tok | {r['documentos_detectados']} peças")
        else:
            print(f" | ERRO: {r.get('erro', '?')}")

    def tempo_total(self):
        t = time.time() - self.inicio
        h, m, s = int(t // 3600), int((t % 3600) // 60), int(t % 60)
        return f"{h}h{m:02d}m{s:02d}s" if h else (f"{m}m{s:02d}s" if m else f"{s}s")

# ============================================================
# LIMPEZA
# ============================================================
LIXO_GLOBAL = [
    re.compile(r'Este documento foi gerado pelo usu.rio\s+\S+.*', re.IGNORECASE | re.DOTALL),
    re.compile(r'N.mero do documento:\s*\d+', re.IGNORECASE),
    re.compile(r'https?://pje\.tjba\.jus\.br\S*', re.IGNORECASE),
    re.compile(r'Assinado eletronicamente por:.*?(?=\n\n|\Z)', re.IGNORECASE | re.DOTALL),
    re.compile(r'Num\.\s*\d+\s*-\s*P.g\.\s*\d+', re.IGNORECASE),
    re.compile(r'PODER JUDICI.RIO[\s\n]+TRIBUNAL DE JUSTI.A DO ESTADO DA BAHIA[\s\n]*', re.IGNORECASE),
    re.compile(r'\(documento gerado e assinado automaticamente pelo PJe\)', re.IGNORECASE),
    re.compile(r'Autos n[°º]\s*[\d.\-/]+\s*\n?', re.IGNORECASE),
]

CABECALHO_PECA = [
    re.compile(r'Processo:\s*[\d.\-/]+.*?\n', re.IGNORECASE),
    re.compile(r'.rg.o Julgador:.*?\n', re.IGNORECASE),
    re.compile(r'VARA CRIMINAL DE RIO REAL.*?\n', re.IGNORECASE),
    re.compile(r'Classe:\s*.+?\n', re.IGNORECASE),
]

def limpar(texto, profundo=False):
    if not texto:
        return ""
    for p in LIXO_GLOBAL:
        texto = p.sub('', texto)
    if profundo:
        for p in CABECALHO_PECA:
            texto = p.sub('', texto)
    texto = re.sub(r'\r\n', '\n', texto)
    texto = re.sub(r'[ \t]+\n', '\n', texto)
    texto = re.sub(r'\n{4,}', '\n\n\n', texto)
    linhas = [l.rstrip() for l in texto.split('\n')]
    return '\n'.join(linhas).strip()

# ============================================================
# DETECÇÃO DE SCAN
# ============================================================
def detectar_scan(page, texto_limpo):
    area_pt2 = (page.width or 595) * (page.height or 842)
    chars = len(texto_limpo.replace(' ', '').replace('\n', ''))
    densidade = chars / area_pt2 if area_pt2 > 0 else 0

    imagens = getattr(page, 'images', []) or []
    for img in imagens:
        w = abs((img.get('x1', 0) or 0) - (img.get('x0', 0) or 0))
        h = abs((img.get('bottom', 0) or 0) - (img.get('top', 0) or 0))
        area_img = w * h
        if area_img > 0 and area_pt2 > 0 and (area_img / area_pt2) > SCAN_IMG_MIN_FRAC:
            return True, "imagem_grande"

    if texto_limpo:
        linhas = [l for l in texto_limpo.split('\n') if l.strip()]
        if len(linhas) >= 5:
            curtas = sum(1 for l in linhas if len(l.strip()) < 5)
            if curtas / len(linhas) > SCAN_LINHAS_CURTAS_FRAC:
                return True, "linhas_fragmentadas"

    if chars < MIN_CHARS_PAGINA:
        if chars == 0:
            return False, "vazia"
        return True, f"poucos_chars({chars})"

    if densidade < SCAN_CHARS_POR_AREA * 2 and chars < MIN_CHARS_PAGINA * 3 and imagens:
        return True, "baixa_densidade"

    return False, "texto_normal"

# ============================================================
# CLASSIFICAÇÃO DE PEÇAS
# ============================================================
CLASSIFICADORES = [
    ("DENUNCIA", ["oferece a presente den", "denuncia como incurso", "denúncia como incursa"]),
    ("SENTENCA", ["vistos, etc", "julgo procedente", "julgo improcedente", "condeno o r", "absolvo o r"]),
    ("PRONUNCIA", ["pronuncio o r", "pronuncia o r"]),
    ("ALEGACOES", ["alegações finais", "alegacoes finais", "memoriais"]),
    ("RESPOSTA", ["resposta à acusação", "resposta a acusação", "defesa prévia"]),
    ("RECURSO", ["apelação", "razões recursais", "contrarrazões"]),
    ("LAUDO", ["laudo pericial", "laudo de exame", "exame de corpo de delito"]),
    ("DECISAO", ["decido que", "defiro o pedido", "indefiro o pedido"]),
    ("DESPACHO", ["despacho", "cite-se", "intime-se", "cumpra-se", "designe-se"]),
    ("ATA", ["ata de audiência", "ata de audiencia", "aberta a audiência"]),
    ("CERTIDAO", ["certifico que", "certidão", "certifico e dou fé"]),
    ("INTIMACAO", ["intimação", "fica intimado"]),
    ("OFICIO", ["ofício n", "oficio n"]),
    ("MANDADO", ["mandado de"]),
    ("ALVARA", ["alvará de soltura"]),
    ("PETICAO", ["petição", "peticao"]),
]

def classificar_peca(texto):
    if not texto:
        return None
    t = texto.lower()[:2000]
    for tipo, kws in CLASSIFICADORES:
        if any(kw in t for kw in kws):
            return tipo
    return "DOC"

# ============================================================
# OCR
# ============================================================
def tentar_ocr(pdf_path, pag_num):
    try:
        import fitz
        import pytesseract
        from PIL import Image
        import io
        doc = fitz.open(pdf_path)
        page = doc[pag_num - 1]
        pix = page.get_pixmap(dpi=250)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        doc.close()
        return pytesseract.image_to_string(img, lang='por', config='--psm 1 --oem 3').strip()
    except Exception:
        pass
    try:
        from pdf2image import convert_from_path
        import pytesseract
        images = convert_from_path(pdf_path, first_page=pag_num, last_page=pag_num, dpi=250)
        if images:
            return pytesseract.image_to_string(images[0], lang='por', config='--psm 1 --oem 3').strip()
    except Exception:
        pass
    return ""

# ============================================================
# UTILITÁRIOS
# ============================================================
def extrair_numero(nome):
    m = re.search(r'(\d{7}[-.]?\d{2})[_.](\d{4})[_.](\d{1,2})[_.](\d{2})[_.](\d{4})', nome)
    if m:
        p1 = m.group(1)
        if '-' not in p1 and '.' not in p1:
            p1 = p1[:7] + '-' + p1[7:]
        return f"{p1}.{m.group(2)}.{m.group(3)}.{m.group(4)}.{m.group(5)}"
    return Path(nome).stem

def obter_metadados(pdf_path):
    try:
        from pypdf import PdfReader
        r = PdfReader(pdf_path)
        m = r.metadata or {}
        return {"titulo": str(m.get("/Title", "") or ""),
                "assunto": str(m.get("/Subject", "") or ""),
                "paginas": len(r.pages)}
    except Exception:
        return {"titulo": "", "assunto": "", "paginas": 0}

def extrair_data(texto):
    m = re.search(r'(\d{2}/\d{2}/\d{4})', texto)
    return m.group(1) if m else ""

def primeira_linha(texto, max_chars=120):
    for linha in texto.split('\n'):
        linha = linha.strip()
        if len(linha) > 10:
            return linha[:max_chars]
    return texto[:max_chars]

# ============================================================
# PROCESSAMENTO
# ============================================================
def processar_pdf(pdf_path, progresso=None, ocr_ok=False):
    import pdfplumber

    nome = os.path.basename(pdf_path)
    numero = extrair_numero(nome)
    meta = obter_metadados(pdf_path)
    n_pags = meta["paginas"]

    if n_pags == 0:
        return {"numero": numero, "arquivo": nome, "status": "ERRO", "erro": "PDF sem páginas"}

    if progresso:
        progresso.novo_pdf(progresso.atual, nome, n_pags)

    stats = {"texto": 0, "ocr": 0, "scan": 0, "vazias": 0}
    paginas_proc = []

    try:
        pdf = pdfplumber.open(pdf_path)
    except Exception as e:
        return {"numero": numero, "arquivo": nome, "status": "ERRO", "erro": str(e)}

    for i, page in enumerate(pdf.pages):
        n = i + 1
        try:
            texto_bruto = page.extract_text() or ""
        except Exception:
            texto_bruto = ""

        texto = limpar(texto_bruto)
        eh_scan, razao = detectar_scan(page, texto)

        if eh_scan:
            if razao == "vazia":
                stats["vazias"] += 1
                tipo_prog = "vazia"
            elif ocr_ok:
                texto_ocr = limpar(tentar_ocr(pdf_path, n))
                if len(texto_ocr) >= MIN_CHARS_PAGINA:
                    stats["ocr"] += 1
                    tipo_prog = "ocr"
                    paginas_proc.append((n, texto_ocr, classificar_peca(texto_ocr), False, ""))
                else:
                    stats["scan"] += 1
                    tipo_prog = "scan"
            else:
                stats["scan"] += 1
                tipo_prog = "scan"

            if tipo_prog in ("scan", "vazia"):
                if eh_scan and razao != "vazia":
                    paginas_proc.append((n, "", "SCAN", True, razao))
        elif len(texto) >= MIN_CHARS_PAGINA:
            stats["texto"] += 1
            tipo_prog = "txt"
            paginas_proc.append((n, texto, classificar_peca(texto), False, ""))
        else:
            stats["vazias"] += 1
            tipo_prog = "vazia"

        if progresso:
            progresso.pagina(n, n_pags, tipo_prog)

    pdf.close()

    # Agrupar páginas consecutivas
    atos = []
    atual = None
    for n, texto, tipo, scan, razao in paginas_proc:
        if scan:
            if atual:
                atos.append(atual)
                atual = None
            atos.append({"tipo": "SCAN", "pag_ini": n, "pag_fim": n,
                         "textos": [], "scan": True, "razao": razao})
        elif tipo and tipo == (atual["tipo"] if atual else None):
            atual["pag_fim"] = n
            atual["textos"].append(texto)
        else:
            if atual:
                atos.append(atual)
            atual = {"tipo": tipo or "DOC", "pag_ini": n, "pag_fim": n,
                     "textos": [texto] if texto else [], "scan": False, "razao": ""}
    if atual:
        atos.append(atual)

    # Gerar markdown
    md = _gerar_markdown(numero, nome, meta, n_pags, stats, atos, ocr_ok)
    nome_saida = numero.replace('.', '_').replace('-', '_') + ".md"
    with open(DIR_SAIDA / nome_saida, 'w', encoding='utf-8') as f:
        f.write(md)

    resultado = {
        "numero": numero, "arquivo": nome, "arquivo_saida": nome_saida,
        "total_paginas": n_pags,
        "pags_texto": stats["texto"], "pags_ocr": stats["ocr"],
        "pags_scan": stats["scan"], "pags_vazias": stats["vazias"],
        "documentos_detectados": len([a for a in atos if not a["scan"]]),
        "chars": len(md), "tokens_aprox": len(md) // 4,
        "status": "OK"
    }
    if progresso:
        progresso.concluido(resultado)
    return resultado


def _gerar_markdown(numero, nome, meta, n_pags, stats, atos, ocr_ok):
    partes = []
    partes.append("---")
    partes.append(f'numero: "{numero}"')
    partes.append(f'arquivo: "{nome}"')
    partes.append(f"total_paginas: {n_pags}")
    if meta.get("titulo"):
        partes.append(f'titulo: "{meta["titulo"]}"')
    partes.append(f'gerado_em: "{datetime.now().strftime("%Y-%m-%d %H:%M")}"')
    partes.append("---")
    partes.append("")
    partes.append(f"# Processo {numero}")
    partes.append("")

    if meta.get("assunto"):
        partes.append(f"**Partes:** {meta['assunto']}")
        partes.append("")

    # Índice
    partes.append("## Índice de Peças")
    partes.append("")
    partes.append("| # | Tipo | Páginas | Resumo |")
    partes.append("|---|------|---------|--------|")

    atos_idx = [a for a in atos if a["scan"] or a["textos"]]
    for i, ato in enumerate(atos_idx, 1):
        pags = f"p.{ato['pag_ini']}" if ato['pag_ini'] == ato['pag_fim'] else f"p.{ato['pag_ini']}–{ato['pag_fim']}"
        if ato["scan"]:
            resumo = f"_Escaneada [{ato['razao']}]_"
        elif ato["textos"]:
            resumo = primeira_linha(ato["textos"][0], 80).replace("|", "\\|")
        else:
            resumo = "_sem texto_"
        partes.append(f"| {i} | **{ato['tipo']}** | {pags} | {resumo} |")
    partes.append("")

    # Conteúdo
    partes.append("## Conteúdo das Peças")
    partes.append("")
    for ato in atos_idx:
        pags = f"p. {ato['pag_ini']}" if ato['pag_ini'] == ato['pag_fim'] else f"p. {ato['pag_ini']}–{ato['pag_fim']}"
        if ato["scan"]:
            partes.append(f"### SCAN — {pags}")
            partes.append(f"> Página escaneada: `{ato['razao']}`")
            partes.append("")
            continue
        if not ato["textos"]:
            continue
        texto = limpar('\n\n'.join(ato["textos"]), profundo=True)
        if ato["tipo"] in PECAS_COMPLETAS:
            partes.append(f"### {ato['tipo']} — {pags}")
            partes.append("")
            partes.append(texto)
            partes.append("")
        elif ato["tipo"] in PECAS_RESUMO:
            linhas = texto.split('\n')
            resumo = '\n'.join(l for l in linhas[:5] if l.strip())
            if resumo:
                partes.append(f"### {ato['tipo']} — {pags}")
                partes.append(f"> {resumo.replace(chr(10), chr(10) + '> ')}")
                partes.append("")
        else:
            linhas = texto.split('\n')
            resumo = '\n'.join(l for l in linhas[:3] if l.strip())
            if resumo:
                partes.append(f"### DOC — {pags}")
                partes.append(f"> {resumo.replace(chr(10), chr(10) + '> ')}")
                partes.append("")

    return '\n'.join(partes)


# ============================================================
# MAIN
# ============================================================
def main():
    print()
    print("=" * 60)
    print("  EXTRAÇÃO DE PROCESSOS — PJe/TJBA")
    print("=" * 60)

    deps_ok = True
    try:
        import pdfplumber
        print("  [OK] pdfplumber")
    except ImportError:
        print("  [XX] pdfplumber — pip install pdfplumber")
        deps_ok = False
    try:
        from pypdf import PdfReader
        print("  [OK] pypdf")
    except ImportError:
        print("  [XX] pypdf — pip install pypdf")
        deps_ok = False

    ocr_ok = False
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        print("  [OK] Tesseract OCR")
        ocr_ok = True
    except Exception:
        print("  [!!] Tesseract não disponível — OCR desabilitado")

    if not deps_ok:
        sys.exit(1)

    if not DIR_PDFS.exists() or not list(DIR_PDFS.glob("*.pdf")):
        print(f"\n  [ERRO] Nenhum PDF em '{DIR_PDFS}/'")
        sys.exit(1)

    pdfs = sorted(DIR_PDFS.glob("*.pdf"))
    total = len(pdfs)
    print(f"\n  {total} PDFs encontrados")
    print("  Legenda: # texto  O OCR  S scan  . vazia")
    print("  " + "─" * 55)

    prog = Progresso(total)
    resultados = []
    total_tokens = 0
    erros = 0

    for i, pdf_path in enumerate(pdfs, 1):
        prog.atual = i
        try:
            r = processar_pdf(str(pdf_path), prog, ocr_ok)
            resultados.append(r)
            if r["status"] == "OK":
                total_tokens += r.get("tokens_aprox", 0)
            else:
                erros += 1
        except Exception as e:
            erros += 1
            print(f"\n  [ERRO] {pdf_path.name}: {e}")
            resultados.append({"numero": extrair_numero(pdf_path.name),
                               "arquivo": pdf_path.name, "status": "ERRO", "erro": str(e)})

    ok = sum(1 for r in resultados if r["status"] == "OK")
    mapeamento = {r["numero"]: {"md": r["arquivo_saida"], "paginas": r["total_paginas"],
                                 "tokens": r["tokens_aprox"]}
                  for r in resultados if r["status"] == "OK"}

    with open(MAPEAMENTO_PATH, 'w', encoding='utf-8') as f:
        json.dump(mapeamento, f, ensure_ascii=False, indent=2)
    with open(RELATORIO_PATH, 'w', encoding='utf-8') as f:
        json.dump({"total_pdfs": total, "sucesso": ok, "erros": erros,
                    "total_tokens": total_tokens, "processos": resultados},
                  f, ensure_ascii=False, indent=2)

    print(f"\n\n  {'=' * 55}")
    print(f"  PDFs: {total} ({ok} ok, {erros} erros)")
    print(f"  Tokens: {total_tokens:,} | Tempo: {prog.tempo_total()}")
    print(f"  Saída: {DIR_SAIDA}/")
    print(f"  {'=' * 55}\n")


if __name__ == "__main__":
    main()
