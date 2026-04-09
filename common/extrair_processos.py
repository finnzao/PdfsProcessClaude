#!/usr/bin/env python3
"""
extrair_processos_v2.py — Extrai texto de PDFs de processos judiciais (PJe/TJBA)

MELHORIAS v2:
  1. DETECÇÃO DE SCAN ROBUSTA (5 heurísticas combinadas):
     - Razão texto/área da página (principal)
     - Presença de imagens grandes via pdfplumber
     - Análise de objetos XObject no PDF (PyMuPDF ou pypdf)
     - Densidade de caracteres por linha
     - Fallback: renderizar a página e medir pixels brancos
  2. FORMATO DE SAÍDA EM MARKDOWN ESTRUTURADO:
     - Muito melhor para LLMs do que txt plano
     - Hierarquia clara: cabeçalho > índice > peças
     - Metadados como frontmatter YAML
     - Peças completas com delimitadores claros
     - Compatível com qualquer editor e ferramenta

DEPENDENCIAS:
    pip install pdfplumber pypdf
    pip install pytesseract Pillow         (OCR — recomendado)
    pip install PyMuPDF                    (melhor detecção de scan — opcional)

USO:
    python3 scripts/extrair_processos_v2.py
"""

import os
import re
import csv
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# ============================================================
# CONFIGURAÇÕES
# ============================================================
DIR_PDFS        = Path("pdfs")
DIR_SAIDA       = Path("textos_extraidos")
DIR_SAIDA.mkdir(exist_ok=True)

CSV_PROCESSOS   = "processos_crime_parados_mais_que_100_dias.csv"
RELATORIO_PATH  = Path("relatorio_extracao.json")
MAPEAMENTO_PATH = Path("mapeamento_processos.json")

# Thresholds de detecção de scan
MIN_CHARS_PAGINA        = 50     # mínimo de chars para considerar página com texto
SCAN_CHARS_POR_AREA     = 0.005  # menos que isso (chars/pt²) → provavelmente scan
SCAN_IMG_MIN_FRAC       = 0.3    # imagem cobre >30% da área → candidato a scan
SCAN_LINHAS_CURTAS_FRAC = 0.8    # >80% das linhas têm <5 chars → scan (OCR fragmentado)

# Peças que recebem conteúdo COMPLETO vs RESUMIDO
PECAS_COMPLETAS = {"DENUNCIA", "SENTENCA", "DECISAO", "DESPACHO", "ATA",
                   "PRONUNCIA", "ALEGACOES", "RESPOSTA", "RECURSO", "LAUDO"}
PECAS_RESUMO    = {"CERTIDAO", "INTIMACAO", "OFICIO", "MANDADO", "ALVARA", "PETICAO"}


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
            print(f"  → {r['tokens_aprox']:,} tok | {r['documentos_detectados']} peças | "
                  f"txt:{r['pags_texto']} ocr:{r['pags_ocr']} "
                  f"scan:{r['pags_scan']} vazia:{r['pags_vazias']}")
            if r.get("pags_scan", 0) > 0 and not r.get("ocr_disponivel"):
                print(f"  ⚠ {r['pags_scan']} pág(s) escaneadas sem OCR — instale Tesseract")
        else:
            print(f" | ERRO: {r.get('erro', '?')}")

    def tempo_total(self):
        t = time.time() - self.inicio
        h, m, s = int(t // 3600), int((t % 3600) // 60), int(t % 60)
        return f"{h}h{m:02d}m{s:02d}s" if h else (f"{m}m{s:02d}s" if m else f"{s}s")


# ============================================================
# LIMPEZA DE TEXTO
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

def limpar(texto: str, profundo: bool = False) -> str:
    if not texto:
        return ""
    for p in LIXO_GLOBAL:
        texto = p.sub('', texto)
    if profundo:
        for p in CABECALHO_PECA:
            texto = p.sub('', texto)
    # Normalizar espaços em branco
    texto = re.sub(r'\r\n', '\n', texto)
    texto = re.sub(r'[ \t]+\n', '\n', texto)
    texto = re.sub(r'\n{4,}', '\n\n\n', texto)
    linhas = [l.rstrip() for l in texto.split('\n')]
    return '\n'.join(linhas).strip()


# ============================================================
# DETECÇÃO DE SCAN — 5 HEURÍSTICAS
# ============================================================
def detectar_scan(page, texto_limpo: str) -> tuple[bool, str]:
    """
    Retorna (é_scan: bool, razão: str)
    Usa múltiplas heurísticas para máxima cobertura.
    """
    area_pt2 = (page.width or 595) * (page.height or 842)
    chars = len(texto_limpo.replace(' ', '').replace('\n', ''))

    # ── Heurística 1: densidade de caracteres por área ──────────────
    densidade = chars / area_pt2 if area_pt2 > 0 else 0
    if chars < MIN_CHARS_PAGINA and densidade < SCAN_CHARS_POR_AREA:
        # Pode ser vazia ou scan — checar imagens antes de decidir
        pass

    # ── Heurística 2: imagens grandes via pdfplumber ─────────────────
    imagens = getattr(page, 'images', []) or []
    for img in imagens:
        # pdfplumber retorna coordenadas em pontos
        w = abs((img.get('x1', 0) or 0) - (img.get('x0', 0) or 0))
        h = abs((img.get('bottom', 0) or 0) - (img.get('top', 0) or 0))
        area_img = w * h
        if area_img > 0 and area_pt2 > 0:
            frac = area_img / area_pt2
            if frac > SCAN_IMG_MIN_FRAC:
                return True, f"imagem_grande({frac:.0%}_da_pagina)"

    # ── Heurística 3: texto fragmentado (OCR ruim ou nenhum) ─────────
    if texto_limpo:
        linhas = [l for l in texto_limpo.split('\n') if l.strip()]
        if len(linhas) >= 5:
            curtas = sum(1 for l in linhas if len(l.strip()) < 5)
            frac_curtas = curtas / len(linhas)
            if frac_curtas > SCAN_LINHAS_CURTAS_FRAC:
                return True, f"linhas_fragmentadas({frac_curtas:.0%})"

    # ── Heurística 4: pouco texto + sem imagens detectadas ───────────
    # Alguns PDFs escaneados não expõem imagens via API mas têm pouco texto
    if chars < MIN_CHARS_PAGINA:
        # Tentar detectar via objetos da página
        try:
            # Acessa o dicionário interno do pdfplumber
            objs = getattr(page, 'objects', {})
            tem_obj_grafico = bool(
                objs.get('rect', []) or
                objs.get('curve', []) or
                objs.get('image', [])
            )
            if tem_obj_grafico:
                return True, "objetos_graficos_sem_texto"
        except Exception:
            pass

        # Se não tem nada → pode ser página em branco mesmo
        # Distinguir: scan tem alguns chars OCR fragments, vazia tem zero
        if chars == 0:
            return False, "vazia"
        else:
            return True, f"poucos_chars({chars})"

    # ── Heurística 5: proporção texto/área muito baixa ───────────────
    # Para páginas que TÊM algum texto mas é suspeito
    if densidade < SCAN_CHARS_POR_AREA * 2 and chars < MIN_CHARS_PAGINA * 3:
        if imagens:  # só confirma se houver alguma imagem
            return True, f"baixa_densidade({densidade:.4f})"

    return False, "texto_normal"


def detectar_scan_fitz(pdf_path: str, pag_num: int) -> tuple[bool, str]:
    """
    Heurística extra usando PyMuPDF (mais preciso para detecção de XObjects).
    Só chamada se pdfplumber não for conclusivo.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        page = doc[pag_num - 1]

        # Verificar se a página tem imagens no XObject dictionary
        xobjs = page.get_xobjects()
        tem_imagem = any(x[1].startswith('/Image') or 'Image' in str(x) for x in xobjs)

        # Verificar se a página renderizada tem muito branco (scan em branco)
        if not tem_imagem:
            # Renderizar a baixa resolução para checar
            clip = fitz.Rect(0, 0, page.rect.width, page.rect.height)
            mat = fitz.Matrix(0.2, 0.2)  # 20% — só para checar
            pix = page.get_pixmap(matrix=mat, clip=clip)
            samples = pix.samples
            total = len(samples)
            if total > 0:
                brancos = sum(1 for b in samples if b > 250)
                frac_branco = brancos / total
                if frac_branco > 0.95:  # quase tudo branco = página vazia
                    doc.close()
                    return False, "pagina_branca_renderizada"

        doc.close()
        if tem_imagem:
            return True, "xobject_imagem_fitz"
        return False, "sem_imagem_fitz"
    except Exception:
        return False, "fitz_indisponivel"


# ============================================================
# CLASSIFICAÇÃO DE PEÇAS
# ============================================================
CLASSIFICADORES = [
    ("DENUNCIA",   ["oferece a presente den", "denuncia como incurso", "denúncia como incursa",
                    "o ministério público", "promotor de justiça"]),
    ("SENTENCA",   ["vistos, etc", "vistos e relatados", "julgo procedente",
                    "julgo improcedente", "condeno o réu", "condeno o r", "absolvo o r",
                    "absolvo o réu", "dispositivo", "ante o exposto"]),
    ("PRONUNCIA",  ["pronuncio o r", "pronuncia o r", "pronunciado", "pronúncia"]),
    ("ALEGACOES",  ["alegações finais", "alegacoes finais", "memoriais", "razões finais"]),
    ("RESPOSTA",   ["resposta à acusação", "resposta a acusação", "defesa prévia",
                    "defesa previa", "resposta da defesa"]),
    ("RECURSO",    ["apelação", "apelacao", "razões recursais", "contrarrazões",
                    "contrarrazoes", "recurso em sentido"]),
    ("LAUDO",      ["laudo pericial", "laudo de exame", "exame de corpo de delito",
                    "perito", "quesitos", "laudo toxicológico"]),
    ("DECISAO",    ["decido que", "defiro o pedido", "indefiro o pedido",
                    "despacho decisório", "decido", "decisão interlocutória"]),
    ("DESPACHO",   ["despacho", "cite-se", "intime-se", "cumpra-se", "designe-se",
                    "vista ao ministério", "vista à defesa", "conclusos"]),
    ("ATA",        ["ata de audiência", "ata de audiencia", "aberta a audiência",
                    "termo de audiência", "iniciada a audiência"]),
    ("CERTIDAO",   ["certifico que", "certidão", "certifico e dou fé"]),
    ("INTIMACAO",  ["intimação", "fica intimado", "ficam intimados", "intimo"]),
    ("OFICIO",     ["ofício n", "oficio n", "sirvo-me do presente"]),
    ("MANDADO",    ["mandado de", "em cumprimento ao mandado"]),
    ("ALVARA",     ["alvará de soltura", "alvarará"]),
    ("PETICAO",    ["petição", "peticao", "requer a vossa excelência"]),
]

def classificar_peca(texto: str) -> str | None:
    if not texto:
        return None
    t = texto.lower()[:2000]  # só os primeiros 2000 chars
    for tipo, kws in CLASSIFICADORES:
        if any(kw in t for kw in kws):
            return tipo
    return "DOC"


# ============================================================
# OCR
# ============================================================
def tentar_ocr(pdf_path: str, pag_num: int, ocr_engine: str) -> str:
    """Tenta OCR em ordem de qualidade: fitz → pdf2image → pypdf+PIL"""

    # Motor 1: PyMuPDF (melhor qualidade de renderização)
    if ocr_engine in ("fitz", "auto"):
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
            texto = pytesseract.image_to_string(img, lang='por',
                config='--psm 1 --oem 3')
            return texto.strip()
        except ImportError:
            pass
        except Exception:
            pass

    # Motor 2: pdf2image + Tesseract
    if ocr_engine in ("pdf2image", "auto"):
        try:
            from pdf2image import convert_from_path
            import pytesseract
            images = convert_from_path(pdf_path, first_page=pag_num,
                                       last_page=pag_num, dpi=250)
            if images:
                texto = pytesseract.image_to_string(images[0], lang='por',
                    config='--psm 1 --oem 3')
                return texto.strip()
        except ImportError:
            pass
        except Exception:
            pass

    # Motor 3: pypdf → PIL (fallback)
    try:
        from pypdf import PdfReader
        import pytesseract
        from PIL import Image
        import io
        reader = PdfReader(pdf_path)
        page = reader.pages[pag_num - 1]
        for img_obj in page.images:
            img = Image.open(io.BytesIO(img_obj.data))
            if img.width > 300 and img.height > 300:
                texto = pytesseract.image_to_string(img, lang='por',
                    config='--psm 1 --oem 3')
                if texto.strip():
                    return texto.strip()
    except Exception:
        pass

    return ""


# ============================================================
# UTILITÁRIOS
# ============================================================
def extrair_numero(nome: str) -> str:
    m = re.search(r'(\d{7}[-.]?\d{2})[_.](\d{4})[_.](\d{1,2})[_.](\d{2})[_.](\d{4})', nome)
    if m:
        p1 = m.group(1)
        if '-' not in p1 and '.' not in p1:
            p1 = p1[:7] + '-' + p1[7:]
        return f"{p1}.{m.group(2)}.{m.group(3)}.{m.group(4)}.{m.group(5)}"
    return Path(nome).stem

def obter_metadados(pdf_path: str) -> dict:
    try:
        from pypdf import PdfReader
        r = PdfReader(pdf_path)
        m = r.metadata or {}
        return {
            "titulo":  str(m.get("/Title",   "") or ""),
            "assunto": str(m.get("/Subject", "") or ""),
            "paginas": len(r.pages),
        }
    except Exception:
        return {"titulo": "", "assunto": "", "paginas": 0}

def extrair_data(texto: str) -> str:
    m = re.search(r'(\d{2}/\d{2}/\d{4})', texto)
    return m.group(1) if m else ""

def primeira_linha(texto: str, max_chars: int = 120) -> str:
    for linha in texto.split('\n'):
        linha = linha.strip()
        if len(linha) > 10:
            return linha[:max_chars]
    return texto[:max_chars]


# ============================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================
def processar_pdf(pdf_path: str, progresso: Progresso | None = None,
                  ocr_disponivel: bool = False) -> dict:
    import pdfplumber

    nome    = os.path.basename(pdf_path)
    numero  = extrair_numero(nome)
    meta    = obter_metadados(pdf_path)
    n_pags  = meta["paginas"]

    if n_pags == 0:
        return {"numero": numero, "arquivo": nome, "status": "ERRO",
                "erro": "PDF sem páginas ou corrompido"}

    if progresso:
        progresso.novo_pdf(progresso.atual, nome, n_pags)

    # ── Determinar motor de OCR disponível ──────────────────────────
    ocr_motor = "nenhum"
    if ocr_disponivel:
        try:
            import fitz
            ocr_motor = "fitz"
        except ImportError:
            try:
                import pdf2image
                ocr_motor = "pdf2image"
            except ImportError:
                ocr_motor = "pypdf"

    stats = {"texto": 0, "ocr": 0, "scan": 0, "vazias": 0, "ocr_fail": 0}
    paginas_proc = []  # [(n, texto, tipo_peca, eh_scan, razao_scan)]

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

        # ── Confirmar scan via fitz se disponível e caso ambíguo ────
        if not eh_scan and len(texto) < MIN_CHARS_PAGINA * 2:
            try:
                import fitz
                eh_scan_fitz, razao_fitz = detectar_scan_fitz(pdf_path, n)
                if eh_scan_fitz:
                    eh_scan, razao = True, razao_fitz
            except ImportError:
                pass

        if eh_scan:
            if razao == "vazia":
                stats["vazias"] += 1
                tipo_prog = "vazia"
                texto_final = ""
                tipo_peca = None
            elif ocr_disponivel:
                texto_ocr = tentar_ocr(pdf_path, n, ocr_motor)
                texto_ocr_limpo = limpar(texto_ocr)
                if len(texto_ocr_limpo) >= MIN_CHARS_PAGINA:
                    stats["ocr"] += 1
                    tipo_prog = "ocr"
                    texto_final = texto_ocr_limpo
                    tipo_peca = classificar_peca(texto_ocr_limpo)
                else:
                    stats["ocr_fail"] += 1
                    stats["scan"] += 1
                    tipo_prog = "ocr_fail"
                    texto_final = ""
                    tipo_peca = None
            else:
                stats["scan"] += 1
                tipo_prog = "scan"
                texto_final = ""
                tipo_peca = None

            paginas_proc.append((n, texto_final, tipo_peca, True, razao))

        elif len(texto) >= MIN_CHARS_PAGINA:
            stats["texto"] += 1
            tipo_prog = "txt"
            tipo_peca = classificar_peca(texto)
            paginas_proc.append((n, texto, tipo_peca, False, ""))
        else:
            stats["vazias"] += 1
            tipo_prog = "vazia"
            paginas_proc.append((n, "", None, False, "vazia"))

        if progresso:
            progresso.pagina(n, n_pags, tipo_prog)

    pdf.close()

    # ── Agrupar páginas consecutivas do mesmo tipo de peça ──────────
    atos = []  # [{"tipo", "pag_ini", "pag_fim", "textos": [], "scan": bool, "razao": str}]
    atual = None

    for n, texto, tipo, eh_scan, razao in paginas_proc:
        if not tipo:
            if atual:
                atos.append(atual)
                atual = None
            if eh_scan and razao != "vazia":
                atos.append({"tipo": "SCAN", "pag_ini": n, "pag_fim": n,
                             "textos": [], "scan": True, "razao": razao})
            continue

        if atual and atual["tipo"] == tipo and not eh_scan:
            atual["pag_fim"] = n
            atual["textos"].append(texto)
        else:
            if atual:
                atos.append(atual)
            atual = {"tipo": tipo, "pag_ini": n, "pag_fim": n,
                    "textos": [texto] if texto else [], "scan": eh_scan, "razao": razao}

    if atual:
        atos.append(atual)

    # ── GERAR SAÍDA MARKDOWN ESTRUTURADO ────────────────────────────
    md = gerar_markdown(numero, nome, meta, n_pags, stats, atos, ocr_disponivel)

    nome_saida = numero.replace('.', '_').replace('-', '_') + ".md"
    with open(DIR_SAIDA / nome_saida, 'w', encoding='utf-8') as f:
        f.write(md)

    chars_total = len(md)
    tokens_aprox = chars_total // 4

    resultado = {
        "numero": numero, "arquivo": nome, "arquivo_saida": nome_saida,
        "total_paginas": n_pags,
        "pags_texto": stats["texto"], "pags_ocr": stats["ocr"],
        "pags_scan": stats["scan"], "pags_vazias": stats["vazias"],
        "ocr_falhas": stats["ocr_fail"],
        "documentos_detectados": len([a for a in atos if not a["scan"]]),
        "chars": chars_total, "tokens_aprox": tokens_aprox,
        "ocr_disponivel": ocr_disponivel,
        "status": "OK"
    }

    if progresso:
        progresso.concluido(resultado)

    return resultado


# ============================================================
# GERADOR DE MARKDOWN
# ============================================================
def gerar_markdown(numero: str, nome: str, meta: dict, n_pags: int,
                   stats: dict, atos: list, ocr_disponivel: bool) -> str:
    partes = []

    # ── FRONTMATTER YAML ─────────────────────────────────────────────
    partes.append("---")
    partes.append(f"numero: \"{numero}\"")
    partes.append(f"arquivo: \"{nome}\"")
    partes.append(f"total_paginas: {n_pags}")
    if meta.get("titulo"):
        titulo_esc = meta["titulo"].replace('"', '\\"')
        partes.append(f"titulo: \"{titulo_esc}\"")
    if meta.get("assunto"):
        assunto_esc = meta["assunto"].replace('"', '\\"')
        partes.append(f"partes: \"{assunto_esc}\"")
    partes.append(f"paginas_texto: {stats['texto']}")
    partes.append(f"paginas_ocr: {stats['ocr']}")
    partes.append(f"paginas_scan_sem_ocr: {stats['scan']}")
    partes.append(f"paginas_vazias: {stats['vazias']}")
    partes.append(f"gerado_em: \"{datetime.now().strftime('%Y-%m-%d %H:%M')}\"")
    if stats["scan"] > 0 and not ocr_disponivel:
        partes.append("aviso: \"ATENÇÃO: páginas escaneadas sem OCR — instale Tesseract para recuperar texto\"")
    partes.append("---")
    partes.append("")

    # ── CABEÇALHO ────────────────────────────────────────────────────
    partes.append(f"# Processo {numero}")
    partes.append("")
    if meta.get("assunto"):
        partes.append(f"**Partes:** {meta['assunto']}")
        partes.append("")

    # ── ÍNDICE DE PEÇAS ──────────────────────────────────────────────
    partes.append("## Índice de Peças Processuais")
    partes.append("")
    partes.append("| # | Tipo | Páginas | Resumo |")
    partes.append("|---|------|---------|--------|")

    atos_indexados = [a for a in atos if not (not a["scan"] and not a["textos"])]
    for i, ato in enumerate(atos_indexados, 1):
        pags = (f"p.{ato['pag_ini']}" if ato['pag_ini'] == ato['pag_fim']
                else f"p.{ato['pag_ini']}–{ato['pag_fim']}")
        if ato["scan"]:
            resumo = f"_Página escaneada [{ato['razao']}]_"
        elif ato["textos"]:
            resumo = primeira_linha(ato["textos"][0], 80)
            resumo = resumo.replace("|", "\\|")
        else:
            resumo = "_sem texto_"
        partes.append(f"| {i} | **{ato['tipo']}** | {pags} | {resumo} |")

    partes.append("")

    # ── CRONOLOGIA COMPACTA ──────────────────────────────────────────
    partes.append("## Cronologia dos Atos")
    partes.append("")
    partes.append("```")
    for ato in atos_indexados:
        pags = (f"p.{ato['pag_ini']:>4}" if ato['pag_ini'] == ato['pag_fim']
                else f"p.{ato['pag_ini']:>3}–{ato['pag_fim']:<3}")
        if ato["scan"]:
            partes.append(f"{pags} | {'SCAN':>12} | [imagem escaneada — {ato['razao']}]")
        elif ato["textos"]:
            data  = extrair_data(ato["textos"][0])
            linha = primeira_linha(ato["textos"][0], 100)
            partes.append(f"{pags} | {ato['tipo']:>12} | {data:>10} | {linha}")
        else:
            partes.append(f"{pags} | {ato['tipo']:>12} | (sem texto extraído)")
    partes.append("```")
    partes.append("")

    # ── CONTEÚDO DAS PEÇAS ──────────────────────────────────────────
    partes.append("## Conteúdo das Peças")
    partes.append("")

    for ato in atos_indexados:
        pags = (f"p. {ato['pag_ini']}" if ato['pag_ini'] == ato['pag_fim']
                else f"p. {ato['pag_ini']}–{ato['pag_fim']}")

        if ato["scan"]:
            partes.append(f"### 🖼 SCAN — {pags}")
            partes.append("")
            partes.append(f"> ⚠️ Página(s) escaneada(s). Razão: `{ato['razao']}`.")
            if not ocr_disponivel:
                partes.append("> OCR não disponível. Instale Tesseract para recuperar o texto.")
            partes.append("")
            continue

        if not ato["textos"]:
            continue

        texto_completo = limpar('\n\n'.join(ato["textos"]), profundo=True)

        if ato["tipo"] in PECAS_COMPLETAS:
            # Conteúdo COMPLETO
            partes.append(f"### {ato['tipo']} — {pags}")
            partes.append("")
            partes.append(texto_completo)
            partes.append("")

        elif ato["tipo"] in PECAS_RESUMO:
            # Resumo (primeiras 5 linhas)
            linhas = texto_completo.split('\n')
            resumo = '\n'.join(l for l in linhas[:5] if l.strip())
            if resumo:
                partes.append(f"### {ato['tipo']} — {pags}")
                partes.append("")
                partes.append(f"> {resumo.replace(chr(10), chr(10) + '> ')}")
                partes.append("")

        else:
            # DOC genérico — resumo curto
            linhas = texto_completo.split('\n')
            resumo = '\n'.join(l for l in linhas[:3] if l.strip())
            if resumo:
                partes.append(f"### DOC — {pags}")
                partes.append("")
                partes.append(f"> {resumo.replace(chr(10), chr(10) + '> ')}")
                partes.append("")

    return '\n'.join(partes)


# ============================================================
# MAIN
# ============================================================
def main():
    print()
    print("=" * 62)
    print("  EXTRAÇÃO DE PROCESSOS JUDICIAIS — PJe/TJBA  v2")
    print("  Detecção robusta de scan + saída Markdown estruturada")
    print("=" * 62)
    print()

    # ── Verificar dependências ───────────────────────────────────────
    print("  Dependências:")
    deps_ok = True

    try:
        import pdfplumber
        print("  [OK] pdfplumber")
    except ImportError:
        print("  [XX] pdfplumber — rode: pip install pdfplumber")
        deps_ok = False

    try:
        from pypdf import PdfReader
        print("  [OK] pypdf")
    except ImportError:
        print("  [XX] pypdf — rode: pip install pypdf")
        deps_ok = False

    ocr_disponivel = False
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        print("  [OK] pytesseract + Tesseract (OCR ativo)")
        ocr_disponivel = True
    except ImportError:
        print("  [!!] pytesseract não instalado — OCR desabilitado")
    except Exception:
        print("  [!!] Tesseract não encontrado — OCR desabilitado")
        print("       Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-por")

    try:
        import fitz
        print("  [OK] PyMuPDF (detecção de scan aprimorada)")
    except ImportError:
        print("  [!!] PyMuPDF ausente (detecção de scan básica)")
        print("       Instale: pip install PyMuPDF  [recomendado]")

    if not deps_ok:
        print("\n  [ERRO] Dependências obrigatórias faltando.")
        sys.exit(1)

    if not ocr_disponivel:
        print("\n  ⚠️  OCR desabilitado. Páginas escaneadas serão marcadas como SCAN.")
        print("     Para habilitar: pip install pytesseract")
        print("     + sudo apt install tesseract-ocr tesseract-ocr-por")

    # ── Localizar PDFs ───────────────────────────────────────────────
    if not DIR_PDFS.exists():
        print(f"\n  [ERRO] Pasta '{DIR_PDFS}' não encontrada.")
        sys.exit(1)

    pdfs = sorted(DIR_PDFS.glob("*.pdf"))
    if not pdfs:
        print(f"\n  [ERRO] Nenhum PDF em '{DIR_PDFS}/'")
        sys.exit(1)

    total = len(pdfs)
    print(f"\n  {total} PDFs encontrados")
    print(f"  Saída: {DIR_SAIDA}/ (formato .md)")
    print()
    print("  Legenda: # texto  O OCR  S scan-sem-OCR  X OCR-falhou  . vazia")
    print("  " + "─" * 58)

    # ── Processar ────────────────────────────────────────────────────
    prog = Progresso(total)
    resultados = []
    total_tokens = 0
    erros = 0

    for i, pdf_path in enumerate(pdfs, 1):
        prog.atual = i
        try:
            r = processar_pdf(str(pdf_path), prog, ocr_disponivel)
            resultados.append(r)
            if r["status"] == "OK":
                total_tokens += r.get("tokens_aprox", 0)
            else:
                erros += 1
        except Exception as e:
            import traceback
            erros += 1
            print(f"\n  [ERRO] {pdf_path.name}: {e}")
            if os.environ.get("DEBUG"):
                traceback.print_exc()
            resultados.append({
                "numero": extrair_numero(pdf_path.name),
                "arquivo": pdf_path.name,
                "status": "ERRO", "erro": str(e)
            })

    # ── Salvar mapeamento e relatório ────────────────────────────────
    ok = sum(1 for r in resultados if r["status"] == "OK")
    mapeamento = {
        r["numero"]: {
            "md": r["arquivo_saida"],
            "paginas": r["total_paginas"],
            "tokens": r["tokens_aprox"],
            "docs": r["documentos_detectados"],
            "scan_sem_ocr": r["pags_scan"],
        }
        for r in resultados if r["status"] == "OK"
    }
    with open(MAPEAMENTO_PATH, 'w', encoding='utf-8') as f:
        json.dump(mapeamento, f, ensure_ascii=False, indent=2)

    with open(RELATORIO_PATH, 'w', encoding='utf-8') as f:
        json.dump({
            "versao": "v2",
            "total_pdfs": total, "sucesso": ok, "erros": erros,
            "total_tokens": total_tokens,
            "ocr_disponivel": ocr_disponivel,
            "processos": resultados
        }, f, ensure_ascii=False, indent=2)

    # ── Resumo final ──────────────────────────────────────────────────
    total_pags  = sum(r.get("total_paginas", 0) for r in resultados if r["status"] == "OK")
    total_scan  = sum(r.get("pags_scan", 0)     for r in resultados if r["status"] == "OK")
    total_ocr   = sum(r.get("pags_ocr", 0)      for r in resultados if r["status"] == "OK")
    total_vazia = sum(r.get("pags_vazias", 0)   for r in resultados if r["status"] == "OK")

    print()
    print()
    print("  =" * 31)
    print("  RESUMO DA EXTRAÇÃO v2")
    print("  =" * 31)
    print(f"  PDFs:            {total} total  |  {ok} OK  |  {erros} erros")
    print(f"  Páginas total:   {total_pags:,}")
    print(f"    Com texto:     {sum(r.get('pags_texto',0) for r in resultados if r['status']=='OK'):,}")
    print(f"    Com OCR:       {total_ocr:,}")
    print(f"    Scan s/ OCR:   {total_scan:,}{'  ← instale Tesseract!' if total_scan > 0 and not ocr_disponivel else ''}")
    print(f"    Vazias:        {total_vazia:,}")
    print(f"  Tokens (aprox):  {total_tokens:,}")
    print(f"  Média/processo:  ~{total_tokens//max(ok,1):,} tokens")
    print(f"  Tempo:           {prog.tempo_total()}")
    print(f"  Formato saída:   Markdown estruturado (.md)")
    print(f"  Diretório:       {DIR_SAIDA}/")
    print(f"  Mapeamento:      {MAPEAMENTO_PATH}")
    if erros:
        print(f"\n  ⚠️  {erros} PDFs com erro — veja {RELATORIO_PATH}")
    print("  " + "=" * 60)
    print()


if __name__ == "__main__":
    main()