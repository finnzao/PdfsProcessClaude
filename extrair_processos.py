#!/usr/bin/env python3
"""
extrair_processos.py - Extrai texto de PDFs de processos judiciais (PJe/TJBA)
Remove cabecalhos/rodapes repetitivos, aplica OCR quando necessario,
gera arquivos .txt limpos com referencia de pagina.

100% Python — nao depende de pdftotext, pdftoppm, pdfinfo, tesseract CLI.

DEPENDENCIAS (pip install):
    pip install pdfplumber pypdf Pillow pytesseract
    (pytesseract so e necessario se houver paginas escaneadas)

USO:
    python scripts/extrair_processos.py
"""

import os
import re
import csv
import sys
import json
import time
import traceback
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

MIN_CHARS_TEXTO = 30

# ============================================================
# PROGRESSO
# ============================================================

class Progresso:
    """Exibe progresso em tempo real no terminal."""

    def __init__(self, total_pdfs):
        self.total_pdfs = total_pdfs
        self.pdf_atual = 0
        self.pdf_nome = ""
        self.pag_atual = 0
        self.pag_total = 0
        self.inicio = time.time()
        self.inicio_pdf = time.time()

    def novo_pdf(self, indice, nome, total_paginas):
        self.pdf_atual = indice
        self.pdf_nome = nome
        self.pag_atual = 0
        self.pag_total = total_paginas
        self.inicio_pdf = time.time()
        pct_global = ((indice - 1) / self.total_pdfs) * 100
        print(f"\n[{indice}/{self.total_pdfs}] ({pct_global:.1f}%) {nome}")
        print(f"  {total_paginas} paginas | ", end="", flush=True)

    def pagina(self, pag_num, tipo="txt"):
        self.pag_atual = pag_num
        pct_pag = (pag_num / self.pag_total) * 100 if self.pag_total > 0 else 0

        # Barra de progresso compacta a cada 10% ou nas ultimas paginas
        marcadores = {10, 20, 30, 40, 50, 60, 70, 80, 90, 100}
        pct_int = int(pct_pag)
        if pct_int in marcadores or pag_num == self.pag_total or pag_num <= 1:
            if tipo == "ocr":
                marcador = "O"
            elif tipo == "vazia":
                marcador = "."
            else:
                marcador = "#"
            print(marcador, end="", flush=True)

        if pag_num == self.pag_total:
            elapsed = time.time() - self.inicio_pdf
            print(f" | {elapsed:.1f}s", end="", flush=True)

    def pdf_concluido(self, resultado):
        if resultado["status"] == "OK":
            chars = resultado.get("chars", 0)
            tokens = resultado.get("tokens_aprox", 0)
            pecas = resultado.get("documentos_detectados", 0)
            txt = resultado.get("paginas_texto", 0)
            ocr = resultado.get("paginas_ocr", 0)
            vazias = resultado.get("paginas_vazias", 0)
            print(f"\n  OK: {tokens:,} tokens, {pecas} pecas, "
                  f"texto:{txt} ocr:{ocr} vazias:{vazias} -> {resultado['arquivo_saida']}")
        else:
            print(f"\n  ERRO: {resultado.get('erro', '?')}")

    def resumo_tempo(self):
        total = time.time() - self.inicio
        horas = int(total // 3600)
        minutos = int((total % 3600) // 60)
        segundos = int(total % 60)
        if horas > 0:
            return f"{horas}h{minutos:02d}m{segundos:02d}s"
        elif minutos > 0:
            return f"{minutos}m{segundos:02d}s"
        else:
            return f"{segundos}s"


# ============================================================
# PADROES DE LIMPEZA - Rodapes/cabecalhos do PJe-TJBA
# ============================================================
PATTERNS_REMOVER = [
    re.compile(r'Este documento foi gerado pelo usu[a\xe1]rio\s+\S+\s+em\s+\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}', re.IGNORECASE),
    re.compile(r'N[u\xfa]mero do documento:\s*\d+'),
    re.compile(r'https?://pje\.tjba\.jus\.br\S*'),
    re.compile(r'Assinado eletronicamente por:.*?(?=\n|$)'),
    re.compile(r'Num\.\s*\d+\s*-\s*P[a\xe1]g\.\s*\d+'),
]

PATTERNS_SEPARADOR = re.compile(r'^[\s\-_=]{3,}$', re.MULTILINE)


def extrair_numero_processo(nome_arquivo):
    match = re.search(r'(\d{7}[-.]?\d{2})[_.](\d{4})[_.](\d{1,2})[_.](\d{2})[_.](\d{4})', nome_arquivo)
    if match:
        p1 = match.group(1)
        if '-' not in p1 and '.' not in p1:
            p1 = p1[:7] + '-' + p1[7:]
        return f"{p1}.{match.group(2)}.{match.group(3)}.{match.group(4)}.{match.group(5)}"
    return Path(nome_arquivo).stem


def limpar_texto(texto):
    if not texto:
        return ""
    for pattern in PATTERNS_REMOVER:
        texto = pattern.sub('', texto)
    texto = PATTERNS_SEPARADOR.sub('', texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    linhas = [l.rstrip() for l in texto.split('\n')]
    return '\n'.join(linhas).strip()


def detectar_tipo_documento(texto):
    if not texto:
        return "VAZIO"
    t = texto.lower()
    tipos = [
        ("DENUNCIA", ["oferece a presente den", "denuncia como incurso", "denncia"]),
        ("SENTENCA", ["sentena", "vistos, etc", "julgo procedente", "julgo improcedente", "condeno o", "absolvo o"]),
        ("DECISAO", ["deciso interlocutria", "decido que", "defiro o pedido", "indefiro o pedido"]),
        ("DESPACHO", ["despacho", "cite-se", "intime-se", "cumpra-se", "designe-se"]),
        ("ATA DE AUDIENCIA", ["ata de audincia", "ata de audiencia", "aberta a audincia", "aberta a audiencia"]),
        ("CERTIDAO", ["certifico que", "certido"]),
        ("INTIMACAO", ["intimao", "intimacao", "fica intimado", "ficam intimados"]),
        ("ALVARA", ["alvar de soltura", "alvara"]),
        ("MANDADO", ["mandado de"]),
        ("OFICIO", ["ofcio", "oficio", "sirvo-me deste"]),
        ("PETICAO", ["petio", "peticao"]),
        ("RESPOSTA A ACUSACAO", ["resposta  acusao", "resposta a acusacao", "defesa prvia", "defesa previa"]),
        ("ALEGACOES FINAIS", ["alegaes finais", "alegacoes finais", "memoriais"]),
        ("PRONUNCIA", ["pronuncio", "pronncia", "pronuncia"]),
        ("RECURSO", ["apelao", "apelacao", "recurso", "contrarrazes", "contrarrazoes"]),
        ("LAUDO", ["laudo", "percia", "pericia", "perito"]),
    ]
    for tipo, keywords in tipos:
        if any(kw in t for kw in keywords):
            return tipo
    return "OUTRO"


def extrair_com_pdfplumber(pdf_path, progresso=None):
    import pdfplumber
    paginas = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            pag_num = i + 1
            try:
                texto = page.extract_text() or ""
            except Exception:
                texto = ""

            texto_limpo = limpar_texto(texto)
            tem_texto = len(texto_limpo) >= MIN_CHARS_TEXTO

            if progresso:
                if tem_texto:
                    progresso.pagina(pag_num, "txt")
                else:
                    progresso.pagina(pag_num, "vazia")

            paginas.append((pag_num, texto))
    return paginas


def extrair_com_pypdf(pdf_path, progresso=None):
    from pypdf import PdfReader
    paginas = []
    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    for i, page in enumerate(reader.pages):
        pag_num = i + 1
        try:
            texto = page.extract_text() or ""
        except Exception:
            texto = ""

        if progresso:
            progresso.pagina(pag_num, "txt" if texto.strip() else "vazia")

        paginas.append((pag_num, texto))
    return paginas


def tentar_ocr_pagina(pdf_path, pag_num):
    # Metodo 1: PyMuPDF (fitz)
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
        texto = pytesseract.image_to_string(img, lang='por')
        return texto.strip()
    except ImportError:
        pass
    except Exception:
        pass

    # Metodo 2: pdf2image
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, first_page=pag_num, last_page=pag_num, dpi=200)
        if images:
            import pytesseract
            texto = pytesseract.image_to_string(images[0], lang='por')
            return texto.strip()
    except ImportError:
        pass
    except Exception:
        pass

    return ""


def obter_metadados_pdf(pdf_path):
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        meta = reader.metadata or {}
        return {
            "titulo": str(meta.get("/Title", "") or ""),
            "assunto": str(meta.get("/Subject", "") or ""),
            "keywords": str(meta.get("/Keywords", "") or ""),
            "paginas": len(reader.pages),
        }
    except Exception:
        return {"titulo": "", "assunto": "", "keywords": "", "paginas": 0}


def processar_e_salvar(pdf_path, progresso=None, ocr_disponivel=False):
    nome_arquivo = os.path.basename(pdf_path)
    numero = extrair_numero_processo(nome_arquivo)

    # Metadados
    meta = obter_metadados_pdf(pdf_path)
    total_paginas = meta["paginas"]

    if total_paginas == 0:
        return {
            "numero": numero, "arquivo": nome_arquivo,
            "status": "ERRO", "erro": "Sem paginas ou PDF corrompido"
        }

    if progresso:
        progresso.novo_pdf(progresso.pdf_atual, nome_arquivo, total_paginas)

    # Extrair texto
    paginas_raw = []
    try:
        paginas_raw = extrair_com_pdfplumber(pdf_path, progresso)
    except Exception as e1:
        print(f"\n    pdfplumber falhou, tentando pypdf... ({e1})")
        try:
            paginas_raw = extrair_com_pypdf(pdf_path, progresso)
        except Exception as e2:
            return {
                "numero": numero, "arquivo": nome_arquivo,
                "status": "ERRO", "erro": f"Ambas bibliotecas falharam: {e1} / {e2}"
            }

    # Processar cada pagina
    stats = {"texto": 0, "ocr": 0, "vazias": 0, "documentos": []}
    conteudo_paginas = []
    doc_atual = None

    for pag_num, texto_bruto in paginas_raw:
        texto_util = limpar_texto(texto_bruto)

        if len(texto_util) >= MIN_CHARS_TEXTO:
            stats["texto"] += 1
            texto_final = texto_util
        else:
            if ocr_disponivel:
                try:
                    texto_ocr = tentar_ocr_pagina(pdf_path, pag_num)
                    texto_ocr_limpo = limpar_texto(texto_ocr)
                    if len(texto_ocr_limpo) >= MIN_CHARS_TEXTO:
                        stats["ocr"] += 1
                        texto_final = texto_ocr_limpo
                        if progresso:
                            progresso.pagina(pag_num, "ocr")
                    else:
                        stats["vazias"] += 1
                        texto_final = ""
                except Exception:
                    stats["vazias"] += 1
                    texto_final = ""
            else:
                stats["vazias"] += 1
                texto_final = ""

        tipo_doc = detectar_tipo_documento(texto_final) if texto_final else "VAZIO"

        if tipo_doc not in ("OUTRO", "VAZIO"):
            if doc_atual and doc_atual["tipo"] == tipo_doc:
                doc_atual["pag_fim"] = pag_num
            else:
                if doc_atual:
                    stats["documentos"].append(doc_atual)
                doc_atual = {"tipo": tipo_doc, "pag_inicio": pag_num, "pag_fim": pag_num}

        conteudo_paginas.append((pag_num, texto_final, tipo_doc))

    if doc_atual:
        stats["documentos"].append(doc_atual)

    # ============================================================
    # MONTAR ARQUIVO DE SAIDA
    # ============================================================
    saida = []
    saida.append("=" * 80)
    saida.append(f"PROCESSO: {numero}")
    saida.append(f"ARQUIVO: {nome_arquivo}")
    saida.append(f"TOTAL DE PAGINAS: {total_paginas}")
    if meta["titulo"]:
        saida.append(f"TITULO: {meta['titulo']}")
    if meta["assunto"]:
        saida.append(f"PARTES: {meta['assunto']}")
    saida.append(f"PAGINAS COM TEXTO: {stats['texto']} | OCR: {stats['ocr']} | VAZIAS: {stats['vazias']}")
    if not ocr_disponivel and stats["vazias"] > 0:
        saida.append(f"AVISO: Tesseract nao disponivel. {stats['vazias']} paginas sem texto nao puderam ser processadas por OCR.")
    saida.append("=" * 80)

    if stats["documentos"]:
        saida.append("")
        saida.append("INDICE DE PECAS PROCESSUAIS DETECTADAS:")
        saida.append("-" * 50)
        for doc in stats["documentos"]:
            if doc["pag_inicio"] == doc["pag_fim"]:
                saida.append(f"  - {doc['tipo']} -- pag. {doc['pag_inicio']}")
            else:
                saida.append(f"  - {doc['tipo']} -- pags. {doc['pag_inicio']}-{doc['pag_fim']}")
        saida.append("-" * 50)

    saida.append("")
    for pag, texto, tipo in conteudo_paginas:
        if not texto:
            continue
        marcador = f" [{tipo}]" if tipo not in ("OUTRO", "VAZIO") else ""
        saida.append(f"--- [PAG. {pag}]{marcador} ---")
        saida.append(texto)
        saida.append("")

    texto_final_str = '\n'.join(saida)

    nome_saida = numero.replace('.', '_').replace('-', '_') + ".txt"
    caminho_saida = DIR_SAIDA / nome_saida

    with open(caminho_saida, 'w', encoding='utf-8') as f:
        f.write(texto_final_str)

    chars_total = len(texto_final_str)
    tokens_aprox = chars_total // 4

    resultado = {
        "numero": numero,
        "arquivo": nome_arquivo,
        "arquivo_saida": nome_saida,
        "total_paginas": total_paginas,
        "paginas_texto": stats["texto"],
        "paginas_ocr": stats["ocr"],
        "paginas_vazias": stats["vazias"],
        "documentos_detectados": len(stats["documentos"]),
        "chars": chars_total,
        "tokens_aprox": tokens_aprox,
        "status": "OK"
    }

    if progresso:
        progresso.pdf_concluido(resultado)

    return resultado


def main():
    print()
    print("=" * 60)
    print("  EXTRACAO DE PROCESSOS JUDICIAIS - PJe/TJBA")
    print("=" * 60)

    # Verificar dependencias
    print()
    print("  Verificando dependencias...")
    deps_ok = True

    try:
        import pdfplumber
        print("  [OK] pdfplumber")
    except ImportError:
        print("  [XX] pdfplumber nao encontrado. Rode: pip install pdfplumber")
        deps_ok = False

    try:
        from pypdf import PdfReader
        print("  [OK] pypdf")
    except ImportError:
        print("  [XX] pypdf nao encontrado. Rode: pip install pypdf")
        deps_ok = False

    ocr_ok = False
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        print("  [OK] pytesseract + Tesseract OCR")
        ocr_ok = True
    except ImportError:
        print("  [!!] pytesseract nao instalado (OCR indisponivel)")
        print("       Rode: pip install pytesseract")
    except Exception:
        print("  [!!] Tesseract OCR nao encontrado no sistema (OCR indisponivel)")
        print("       Paginas escaneadas serao ignoradas.")

    if not deps_ok:
        print()
        print("  [ERRO] Dependencias obrigatorias faltando.")
        sys.exit(1)

    # Verificar pasta PDFs
    if not DIR_PDFS.exists():
        print(f"\n  [ERRO] Pasta '{DIR_PDFS}' nao encontrada!")
        sys.exit(1)

    pdfs = sorted(DIR_PDFS.glob("*.pdf"))
    if not pdfs:
        print(f"\n  [ERRO] Nenhum PDF encontrado em '{DIR_PDFS}/'")
        sys.exit(1)

    total_pdfs = len(pdfs)
    print(f"\n  {total_pdfs} PDFs encontrados")
    if not ocr_ok:
        print("  [!!] OCR indisponivel. Paginas sem texto serao marcadas como vazias.")

    print()
    print("  Legenda do progresso:")
    print("    # = pagina com texto   O = pagina com OCR   . = pagina vazia")
    print()
    print("  --------------------------------------------------------")

    # Carregar CSV
    dados_csv = {}
    csv_path = Path(CSV_PROCESSOS)
    if csv_path.exists():
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                num = row.get('Numero do Processo', row.get('\u004e\u00famero do Processo', '')).strip()
                if num:
                    dados_csv[num] = row

    # Processar
    progresso = Progresso(total_pdfs)
    resultados = []
    total_tokens = 0
    erros = 0

    for i, pdf_path in enumerate(pdfs, 1):
        progresso.pdf_atual = i
        try:
            resultado = processar_e_salvar(str(pdf_path), progresso, ocr_ok)
            resultados.append(resultado)
            if resultado["status"] == "OK":
                total_tokens += resultado.get("tokens_aprox", 0)
            else:
                erros += 1
        except Exception as e:
            erros += 1
            print(f"\n  [ERRO] {pdf_path.name}: {e}")
            resultados.append({
                "numero": extrair_numero_processo(pdf_path.name),
                "arquivo": pdf_path.name,
                "status": "ERRO",
                "erro": str(e)
            })

    # Mapeamento
    mapeamento = {}
    for r in resultados:
        if r["status"] == "OK":
            mapeamento[r["numero"]] = {
                "txt": r["arquivo_saida"],
                "paginas": r["total_paginas"],
                "tokens": r["tokens_aprox"],
                "docs_detectados": r["documentos_detectados"]
            }

    with open(MAPEAMENTO_PATH, 'w', encoding='utf-8') as f:
        json.dump(mapeamento, f, ensure_ascii=False, indent=2)

    # Relatorio
    ok_count = sum(1 for r in resultados if r["status"] == "OK")
    relatorio = {
        "total_pdfs": total_pdfs,
        "sucesso": ok_count,
        "erros": erros,
        "total_tokens_aprox": total_tokens,
        "processos": resultados
    }
    with open(RELATORIO_PATH, 'w', encoding='utf-8') as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)

    # Resumo final
    tempo = progresso.resumo_tempo()
    total_paginas_all = sum(r.get("total_paginas", 0) for r in resultados if r["status"] == "OK")

    print()
    print()
    print("  ========================================================")
    print("  RESUMO DA EXTRACAO")
    print("  ========================================================")
    print(f"  PDFs processados:  {total_pdfs}")
    print(f"  Sucesso:           {ok_count}")
    print(f"  Erros:             {erros}")
    print(f"  Total de paginas:  {total_paginas_all:,}")
    print(f"  Tokens (aprox):    {total_tokens:,}")
    print(f"  Tempo total:       {tempo}")
    if total_pdfs > 0:
        media = total_tokens // max(ok_count, 1)
        print(f"  Media por PDF:     ~{media:,} tokens")
    print(f"  --------------------------------------------------------")
    print(f"  Saida:       {DIR_SAIDA}/")
    print(f"  Mapeamento:  {MAPEAMENTO_PATH}")
    print(f"  Relatorio:   {RELATORIO_PATH}")
    if erros > 0:
        print(f"\n  [!!] {erros} PDFs com erro. Veja relatorio_extracao.json")
    print("  ========================================================")
    print()


if __name__ == "__main__":
    main()
