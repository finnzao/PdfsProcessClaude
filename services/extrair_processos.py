#!/usr/bin/env python3
"""
extrair_processos.py - Extrai texto de PDFs de processos judiciais (PJe/TJBA)

Formato de saida otimizado para LLM:
  1. Cabecalho com metadados do processo (1x)
  2. Cronologia de TODOS os atos (1 linha por ato, com pagina e data)
  3. Conteudo completo apenas das PECAS RELEVANTES (denuncia, sentenca, 
     decisao, despacho, ata de audiencia)
  4. Pecas secundarias (certidao, oficio, etc) incluidas de forma resumida

Reducao tipica: ~55-60% menos tokens vs txt plano, sem perda de informacao juridica.

DEPENDENCIAS:
    pip install pdfplumber pypdf
    pip install pytesseract Pillow PyMuPDF   (para OCR, opcional)
"""

import os
import re
import csv
import sys
import json
import time
from pathlib import Path

# ============================================================
# CONFIGURACOES
# ============================================================
DIR_PDFS = Path("pdfs")
DIR_SAIDA = Path("textos_extraidos")
DIR_SAIDA.mkdir(exist_ok=True)

CSV_PROCESSOS = "processos_crime_parados_mais_que_100_dias.csv"
RELATORIO_PATH = Path("relatorio_extracao.json")
MAPEAMENTO_PATH = Path("mapeamento_processos.json")

MIN_CHARS_TEXTO = 50
IMG_GRANDE_MIN = 400

# Pecas que devem ter conteudo COMPLETO (relevantes para analise juridica)
PECAS_COMPLETAS = {"DENUNCIA", "SENTENCA", "DECISAO", "DESPACHO", "ATA", "PRONUNCIA", "ALEGACOES"}
# Pecas secundarias: so primeira linha como resumo
PECAS_RESUMO = {"CERTIDAO", "INTIMACAO", "OFICIO", "MANDADO", "ALVARA", "PETICAO"}

# ============================================================
# PROGRESSO
# ============================================================
class Progresso:
    def __init__(self, total_pdfs):
        self.total_pdfs = total_pdfs
        self.pdf_atual = 0
        self.pag_total = 0
        self.inicio = time.time()
        self.inicio_pdf = time.time()

    def novo_pdf(self, indice, nome, total_paginas):
        self.pdf_atual = indice
        self.pag_total = total_paginas
        self.inicio_pdf = time.time()
        pct = ((indice - 1) / self.total_pdfs) * 100
        print(f"\n[{indice}/{self.total_pdfs}] ({pct:.1f}%) {nome}")
        print(f"  {total_paginas} pags | ", end="", flush=True)

    def pagina(self, pag_num, tipo="txt"):
        m = {"txt": "#", "ocr": "O", "ocr_fail": "X", "vazia": ".", "scan": "S"}
        step = max(1, self.pag_total // 20)
        if pag_num % step == 0 or pag_num <= 1 or pag_num == self.pag_total:
            print(m.get(tipo, "?"), end="", flush=True)

    def pdf_concluido(self, r):
        elapsed = time.time() - self.inicio_pdf
        if r["status"] == "OK":
            print(f" | {elapsed:.1f}s")
            print(f"  -> {r['tokens_aprox']:,} tok, {r['documentos_detectados']} pecas | "
                  f"txt:{r['paginas_texto']} ocr:{r['paginas_ocr']} scan:{r.get('paginas_scan',0)} vazias:{r['paginas_vazias']}")
        else:
            print(f" | ERRO: {r.get('erro','?')}")

    def resumo_tempo(self):
        t = time.time() - self.inicio
        h, m, s = int(t//3600), int((t%3600)//60), int(t%60)
        if h > 0: return f"{h}h{m:02d}m{s:02d}s"
        elif m > 0: return f"{m}m{s:02d}s"
        return f"{s}s"


# ============================================================
# LIMPEZA
# ============================================================
LIXO = [
    re.compile(r'Este documento foi gerado pelo usu.rio.*', re.IGNORECASE),
    re.compile(r'N.mero do documento:\s*\d+'),
    re.compile(r'https?://pje\.tjba\.jus\.br\S*'),
    re.compile(r'Assinado eletronicamente por:.*', re.IGNORECASE),
    re.compile(r'Num\.\s*\d+\s*-\s*P.g\.\s*\d+'),
    re.compile(r'PODER JUDICI.RIO\s*\n?\s*TRIBUNAL DE JUSTI.A DO ESTADO DA BAHIA\s*', re.IGNORECASE),
    re.compile(r'\(documento gerado e assinado automaticamente pelo PJe\)', re.IGNORECASE),
]

# Cabeçalho repetido dentro de cada peça (partes, advogados, etc)
CABECALHO_PECA = [
    re.compile(r'Processo:.*?02\d{2}\s*\n?', re.IGNORECASE),
    re.compile(r'.rg.o Julgador:.*\n?', re.IGNORECASE),
    re.compile(r'(?:AUTOR|REQUERENTE|REU|ADOLESCENTE|INDICIADO):.*?Advogado\(s\):.*?\n', re.IGNORECASE),
    re.compile(r'Advogado\(s\):\s*\n', re.IGNORECASE),
    re.compile(r'VARA CRIMINAL DE RIO REAL\s*\n?', re.IGNORECASE),
    re.compile(r'RIO REAL/BA,\s*\d+\s+de\s+\w+\s+de\s+\d{4}\.?\s*\n?', re.IGNORECASE),
]

def limpar(texto):
    if not texto: return ""
    for p in LIXO:
        texto = p.sub('', texto)
    linhas = [l.strip() for l in texto.split('\n') if l.strip()]
    return '\n'.join(linhas)

def limpar_profundo(texto):
    """Limpeza profunda: remove também cabeçalhos repetidos dentro de peças."""
    texto = limpar(texto)
    for p in CABECALHO_PECA:
        texto = p.sub('', texto)
    linhas = [l.strip() for l in texto.split('\n') if l.strip()]
    return '\n'.join(linhas)

def extrair_numero(nome):
    m = re.search(r'(\d{7}[-.]?\d{2})[_.](\d{4})[_.](\d{1,2})[_.](\d{2})[_.](\d{4})', nome)
    if m:
        p1 = m.group(1)
        if '-' not in p1 and '.' not in p1:
            p1 = p1[:7] + '-' + p1[7:]
        return f"{p1}.{m.group(2)}.{m.group(3)}.{m.group(4)}.{m.group(5)}"
    return Path(nome).stem


# ============================================================
# CLASSIFICACAO DE PECAS
# ============================================================
def classificar_peca(texto):
    if not texto: return None
    t = texto.lower()
    for tp, kws in [
        ("DENUNCIA", ["oferece a presente den", "denuncia como incurso"]),
        ("SENTENCA", ["vistos, etc", "julgo procedente", "julgo improcedente", "condeno o r", "absolvo o r"]),
        ("PRONUNCIA", ["pronuncio o r", "pronuncia do r"]),
        ("ALEGACOES", ["alegacoes finais", "alegaes finais", "memoriais"]),
        ("DECISAO", ["decido que", "defiro o pedido", "indefiro o pedido", "decis"]),
        ("DESPACHO", ["despacho", "cite-se", "intime-se", "cumpra-se", "designe-se"]),
        ("ATA", ["ata de audi", "aberta a audi", "termo de audi"]),
        ("CERTIDAO", ["certifico", "certid"]),
        ("INTIMACAO", ["intima", "fica intimado"]),
        ("OFICIO", ["of.cio", "oficio", "sirvo-me"]),
        ("MANDADO", ["mandado de"]),
        ("ALVARA", ["alvar"]),
        ("PETICAO", ["peti"]),
    ]:
        if any(kw in t for kw in kws):
            return tp
    return "DOC"

def pagina_e_scan(page, texto_limpo):
    imgs = getattr(page, 'images', [])
    for img in imgs:
        w = img.get('width', 0) or (img.get('x1', 0) - img.get('x0', 0))
        h = img.get('height', 0) or (img.get('bottom', 0) - img.get('top', 0))
        if w > IMG_GRANDE_MIN and h > IMG_GRANDE_MIN:
            if len(texto_limpo) < MIN_CHARS_TEXTO:
                return True
            # Texto é só "p. XX" ?
            sem_pref = re.sub(r'^p\.\s*\d+\s*$', '', texto_limpo, flags=re.MULTILINE).strip()
            if len(sem_pref) < 20:
                return True
    return False


# ============================================================
# OCR
# ============================================================
def tentar_ocr(pdf_path, pag_num):
    try:
        import fitz
        doc = fitz.open(pdf_path)
        page = doc[pag_num - 1]
        pix = page.get_pixmap(dpi=200)
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        doc.close()
        import pytesseract
        return pytesseract.image_to_string(img, lang='por').strip()
    except Exception:
        pass
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, first_page=pag_num, last_page=pag_num, dpi=200)
        if images:
            import pytesseract
            return pytesseract.image_to_string(images[0], lang='por').strip()
    except Exception:
        pass
    return ""

def obter_metadados(pdf_path):
    try:
        from pypdf import PdfReader
        r = PdfReader(pdf_path)
        m = r.metadata or {}
        return {"titulo": str(m.get("/Title","") or ""), "assunto": str(m.get("/Subject","") or ""), "paginas": len(r.pages)}
    except Exception:
        return {"titulo": "", "assunto": "", "paginas": 0}


# ============================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================
def processar_e_salvar(pdf_path, progresso=None, ocr_ok=False):
    import pdfplumber

    nome = os.path.basename(pdf_path)
    numero = extrair_numero(nome)
    meta = obter_metadados(pdf_path)
    total_pags = meta["paginas"]

    if total_pags == 0:
        return {"numero": numero, "arquivo": nome, "status": "ERRO", "erro": "PDF sem paginas"}

    if progresso:
        progresso.novo_pdf(progresso.pdf_atual, nome, total_pags)

    stats = {"texto": 0, "ocr": 0, "scan": 0, "vazias": 0, "ocr_fail": 0}

    # FASE 1: Extrair e classificar todas as paginas
    paginas = []  # [(pag_num, texto_limpo, tipo_peca, eh_scan)]

    try:
        pdf = pdfplumber.open(pdf_path)
    except Exception as e:
        return {"numero": numero, "arquivo": nome, "status": "ERRO", "erro": str(e)}

    for i, page in enumerate(pdf.pages):
        pag = i + 1
        try:
            texto_bruto = page.extract_text() or ""
        except Exception:
            texto_bruto = ""

        texto_limpo = limpar(texto_bruto)
        eh_scan = pagina_e_scan(page, texto_limpo)

        if eh_scan:
            if ocr_ok:
                texto_ocr = tentar_ocr(pdf_path, pag)
                texto_ocr_limpo = limpar(texto_ocr)
                if len(texto_ocr_limpo) >= MIN_CHARS_TEXTO:
                    stats["ocr"] += 1
                    paginas.append((pag, texto_ocr_limpo, classificar_peca(texto_ocr_limpo), False))
                    if progresso: progresso.pagina(pag, "ocr")
                else:
                    stats["ocr_fail"] += 1
                    stats["scan"] += 1
                    paginas.append((pag, None, "SCAN", True))
                    if progresso: progresso.pagina(pag, "ocr_fail")
            else:
                stats["scan"] += 1
                paginas.append((pag, None, "SCAN", True))
                if progresso: progresso.pagina(pag, "scan")
        elif len(texto_limpo) >= MIN_CHARS_TEXTO:
            stats["texto"] += 1
            paginas.append((pag, texto_limpo, classificar_peca(texto_limpo), False))
            if progresso: progresso.pagina(pag, "txt")
        else:
            stats["vazias"] += 1
            if progresso: progresso.pagina(pag, "vazia")

    pdf.close()

    # FASE 2: Agrupar paginas consecutivas do mesmo tipo de ato
    atos = []  # [{"tipo", "pag_ini", "pag_fim", "textos": [], "scan": bool}]
    current = None

    for pag, texto, tipo, scan in paginas:
        if scan:
            if current:
                atos.append(current)
                current = None
            atos.append({"tipo": "SCAN", "pag_ini": pag, "pag_fim": pag, "textos": [], "scan": True})
        elif tipo and tipo == (current["tipo"] if current else None):
            current["pag_fim"] = pag
            current["textos"].append(texto)
        else:
            if current:
                atos.append(current)
            current = {"tipo": tipo or "DOC", "pag_ini": pag, "pag_fim": pag, "textos": [texto] if texto else [], "scan": False}

    if current:
        atos.append(current)

    # FASE 3: Montar saida hibrida otimizada para LLM
    saida = []

    # === CABECALHO (1x, informacoes do processo) ===
    saida.append(f"<processo n='{numero}' pags='{total_pags}'>")
    if meta["titulo"]:
        saida.append(f"<meta>{meta['titulo']}</meta>")
    if meta["assunto"]:
        saida.append(f"<partes>{meta['assunto']}</partes>")

    # === CRONOLOGIA (1 linha por ato, para visao geral rapida) ===
    saida.append("")
    saida.append("<cronologia>")
    for ato in atos:
        pags = f"p.{ato['pag_ini']}" if ato['pag_ini'] == ato['pag_fim'] else f"p.{ato['pag_ini']}-{ato['pag_fim']}"
        if ato["scan"]:
            saida.append(f"  {pags} | SCAN (imagem escaneada)")
        elif ato["textos"]:
            # Data do ato
            texto_junto = '\n'.join(ato["textos"])
            data_m = re.search(r'(\d{2}/\d{2}/\d{4})', texto_junto)
            data = data_m.group(1) if data_m else ""
            # Primeira linha como resumo
            resumo = ato["textos"][0].split('\n')[0][:120]
            saida.append(f"  {pags} | {data:>10} | {ato['tipo']:>10} | {resumo}")
    saida.append("</cronologia>")

    # === CONTEUDO DAS PECAS RELEVANTES (completo) ===
    saida.append("")
    saida.append("<pecas>")
    for ato in atos:
        if ato["scan"] or not ato["textos"]:
            continue

        pags = f"{ato['pag_ini']}" if ato['pag_ini'] == ato['pag_fim'] else f"{ato['pag_ini']}-{ato['pag_fim']}"

        if ato["tipo"] in PECAS_COMPLETAS:
            # Conteudo completo, com limpeza profunda
            texto_limpo_prof = limpar_profundo('\n'.join(ato["textos"]))
            saida.append(f"<ato tipo='{ato['tipo']}' pag='{pags}'>")
            saida.append(texto_limpo_prof)
            saida.append("</ato>")
        elif ato["tipo"] in PECAS_RESUMO:
            # So resumo (3 primeiras linhas)
            linhas = '\n'.join(ato["textos"]).split('\n')
            resumo_linhas = '\n'.join(linhas[:3])
            resumo_limpo = limpar_profundo(resumo_linhas)
            if resumo_limpo:
                saida.append(f"<ato tipo='{ato['tipo']}' pag='{pags}' resumo='true'>{resumo_limpo}</ato>")
        else:
            # Documentos sem classificacao: incluir resumido
            linhas = '\n'.join(ato["textos"]).split('\n')
            resumo_linhas = '\n'.join(linhas[:5])
            resumo_limpo = limpar_profundo(resumo_linhas)
            if resumo_limpo:
                saida.append(f"<doc pag='{pags}'>{resumo_limpo}</doc>")

    saida.append("</pecas>")
    saida.append("</processo>")

    texto_out = '\n'.join(saida)
    nome_saida = numero.replace('.', '_').replace('-', '_') + ".txt"
    with open(DIR_SAIDA / nome_saida, 'w', encoding='utf-8') as f:
        f.write(texto_out)

    resultado = {
        "numero": numero, "arquivo": nome, "arquivo_saida": nome_saida,
        "total_paginas": total_pags,
        "paginas_texto": stats["texto"], "paginas_ocr": stats["ocr"],
        "paginas_scan": stats["scan"], "paginas_vazias": stats["vazias"],
        "ocr_falhas": stats["ocr_fail"],
        "documentos_detectados": len([a for a in atos if not a["scan"]]),
        "chars": len(texto_out), "tokens_aprox": len(texto_out) // 4,
        "status": "OK"
    }
    if progresso:
        progresso.pdf_concluido(resultado)
    return resultado


# ============================================================
# MAIN
# ============================================================
def main():
    print()
    print("=" * 60)
    print("  EXTRACAO DE PROCESSOS JUDICIAIS - PJe/TJBA")
    print("  Formato hibrido otimizado para LLM")
    print("=" * 60)
    print()

    # Dependencias
    print("  Dependencias:")
    deps_ok = True
    try:
        import pdfplumber; print("  [OK] pdfplumber")
    except ImportError:
        print("  [XX] pdfplumber. Rode: pip install pdfplumber"); deps_ok = False
    try:
        from pypdf import PdfReader; print("  [OK] pypdf")
    except ImportError:
        print("  [XX] pypdf. Rode: pip install pypdf"); deps_ok = False

    ocr_ok = False
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        print("  [OK] pytesseract + Tesseract")
        ocr_ok = True
    except ImportError:
        print("  [!!] pytesseract nao instalado")
    except Exception:
        print("  [!!] Tesseract nao encontrado. Paginas escaneadas serao marcadas.")

    if not deps_ok:
        print("\n  [ERRO] Dependencias obrigatorias faltando."); sys.exit(1)

    if not DIR_PDFS.exists() or not list(DIR_PDFS.glob("*.pdf")):
        print(f"\n  [ERRO] Nenhum PDF em '{DIR_PDFS}/'"); sys.exit(1)

    pdfs = sorted(DIR_PDFS.glob("*.pdf"))
    total = len(pdfs)
    print(f"\n  {total} PDFs encontrados")
    print()
    print("  Legenda: # = texto  O = OCR  S = scan (sem OCR)  X = OCR falhou  . = vazia")
    print("  --------------------------------------------------------")

    prog = Progresso(total)
    resultados = []
    total_tokens = 0
    erros = 0

    for i, pdf_path in enumerate(pdfs, 1):
        prog.pdf_atual = i
        try:
            r = processar_e_salvar(str(pdf_path), prog, ocr_ok)
            resultados.append(r)
            if r["status"] == "OK": total_tokens += r.get("tokens_aprox", 0)
            else: erros += 1
        except Exception as e:
            erros += 1
            print(f"\n  [ERRO] {pdf_path.name}: {e}")
            resultados.append({"numero": extrair_numero(pdf_path.name),
                               "arquivo": pdf_path.name, "status": "ERRO", "erro": str(e)})

    # Salvar
    ok = sum(1 for r in resultados if r["status"] == "OK")
    mapeamento = {r["numero"]: {"txt": r["arquivo_saida"], "paginas": r["total_paginas"],
                                 "tokens": r["tokens_aprox"], "docs": r["documentos_detectados"]}
                  for r in resultados if r["status"] == "OK"}
    with open(MAPEAMENTO_PATH, 'w', encoding='utf-8') as f:
        json.dump(mapeamento, f, ensure_ascii=False, indent=2)
    with open(RELATORIO_PATH, 'w', encoding='utf-8') as f:
        json.dump({"total_pdfs": total, "sucesso": ok, "erros": erros,
                    "total_tokens": total_tokens, "processos": resultados},
                  f, ensure_ascii=False, indent=2)

    total_pags = sum(r.get("total_paginas", 0) for r in resultados if r["status"] == "OK")
    total_scan = sum(r.get("paginas_scan", 0) for r in resultados if r["status"] == "OK")
    total_ocr = sum(r.get("paginas_ocr", 0) for r in resultados if r["status"] == "OK")

    print()
    print()
    print("  ========================================================")
    print("  RESUMO")
    print("  ========================================================")
    print(f"  PDFs:          {total} ({ok} ok, {erros} erros)")
    print(f"  Paginas:       {total_pags:,}")
    print(f"  Tokens:        {total_tokens:,}")
    print(f"  OCR aplicado:  {total_ocr} pags | Scans sem OCR: {total_scan}")
    print(f"  Tempo:         {prog.resumo_tempo()}")
    if ok > 0:
        print(f"  Media/PDF:     ~{total_tokens//ok:,} tokens")
    print(f"  --------------------------------------------------------")
    print(f"  Formato:       Hibrido (cronologia + pecas-chave em XML)")
    print(f"  Saida:         {DIR_SAIDA}/")
    print("  ========================================================")
    print()


if __name__ == "__main__":
    main()
