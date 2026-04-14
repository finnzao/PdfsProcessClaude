#!/usr/bin/env python3
"""
extrair_processos.py — PDF → Markdown otimizado para LLM.
Motor: pymupdf4llm. Pipeline: extração → captura IDs PJe → limpeza → classificação → markdown compacto.
"""

import os, re, sys, json, time, hashlib
from pathlib import Path
from datetime import datetime

DIR_PDFS = Path(__file__).parent.parent / "pdfs"
DIR_SAIDA = Path(__file__).parent.parent / "textos_extraidos"
RELATORIO_PATH = Path(__file__).parent.parent / "relatorio_extracao.json"
MAPEAMENTO_PATH = Path(__file__).parent.parent / "mapeamento_processos.json"
DIR_SAIDA.mkdir(exist_ok=True)


# — Captura o ID do documento PJe de cada página (Num. XXXXXXX - Pág. X) —
RE_NUM_PAG = re.compile(r'Num[.\s]+(\d{5,})\s*[-–]\s*P[áa]g[.\s]+(\d+)')
RE_NUM_ONLY = re.compile(r'Num[.\s]+(\d{5,})')

def extrair_doc_id(texto):
    """Pega o ID PJe (Num. XXXXXXXXX - Pág. X) do rodapé da página."""
    m = RE_NUM_PAG.findall(texto)
    if m:
        return m[-1]  # (num, pag) — último match (rodapé)
    m2 = RE_NUM_ONLY.findall(texto)
    if m2:
        return (m2[-1], "1")
    return None


# — Lixo PJe/Sinesp removido de cada página —
LIXO = [
    re.compile(r'Este documento foi gerado pelo usu.rio.*?(?=\n|$)', re.I),
    re.compile(r'N[úu]mero do documento:\s*\d+.*?(?=\n|$)', re.I),
    re.compile(r'https?://\S+', re.I),
    re.compile(r'Assinado eletronicamente.*?(?=\n|$)', re.I),
    re.compile(r'Num[.\s]+\d{5,}\s*[-–]\s*P[áa]g[.\s]+\d+', re.I),
    re.compile(r'C[óo]digo Verificador \(MAC\).*?(?=\n|$)', re.I),
    re.compile(r'Pg\.\s*\d+/\d+', re.I),
    re.compile(r'Fls:?\s*\d*\s*\n?\s*Visto:?', re.I),
    re.compile(r'Impresso por:.*?(?=\n|$)', re.I),
    re.compile(r'Data de Impress[ãa]o:.*?(?=\n|$)', re.I),
    re.compile(r'PPe\s*[-–]\s*Procedimentos Policiais.*?(?=\n|$)', re.I),
    re.compile(r'P[áa]gina\s+\d+\s+de\s+\d+', re.I),
    re.compile(r'Gerado por Sinesp Seguran[çc]a', re.I),
    re.compile(r'Documento assinado eletronicamente.*?Bras[íi]lia\.?', re.I | re.DOTALL),
    re.compile(r'O sigilo deste documento.*?administrativas\.?', re.I | re.DOTALL),
    re.compile(r'A autenticidade do documento.*?(?=\n\n|\Z)', re.I | re.DOTALL),
    re.compile(r'Informe o c[óo]digo verificador.*?(?=\n|$)', re.I),
    re.compile(r'Este documento ainda poder[áa].*?(?=\n|$)', re.I),
    re.compile(r'Minist[ée]rio da\s*\n?\s*Justi[çc]a e Seguran[çc]a P[úu]blica', re.I),
    re.compile(r'Secretaria Nacional de\s*\n?\s*Seguran[çc]a P[úu]blica', re.I),
    re.compile(r'TJBA\s*\n?\s*PJe\s*[-–]\s*Processo Judicial.*', re.I),
    re.compile(r'!\[.*?\]\(.*?\)', re.I),
    re.compile(r'^\d{10,}\s*$', re.I | re.M),
    re.compile(r'IP de Registro:.*?(?=\n|$)', re.I),
    re.compile(r'GOVERNO DO ESTADO DA BAHIA\s*\n?\s*POL[ÍI]CIA CIVIL\s*\n?\s*DELEGACIA TERRITORIAL\s*[-–].*?[-–]\s*BA\s*\n?', re.I),
    re.compile(r'GOVERNO DO ESTADO DE SERGIPE\s*\n?\s*POL[ÍI]CIA CIVIL.*?\n', re.I),
    re.compile(r'GOVERNO DO ESTADO DA BAHIA\s*\n?\s*DELEGACIA TERRITORIAL.*?\n', re.I),
    re.compile(r'ESTADO DA BAHIA\s*\n?\s*SECRETARIA DA SEGURAN.A P.BLICA.*?\n', re.I),
    re.compile(r'PODER JUDICI.RIO[\s\n]+TRIBUNAL DE JUSTI.A DO ESTADO DA BAHIA[\s\n]*', re.I),
    re.compile(r'\(documento gerado e assinado automaticamente pelo PJe\)', re.I),
    re.compile(r'Autos n[°º]\s*[\d.\-/]+\s*\n?', re.I),
]

def limpar(texto):
    """Remove cabeçalhos, assinaturas e lixo institucional."""
    for p in LIXO:
        texto = p.sub('', texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    texto = re.sub(r'[ \t]+\n', '\n', texto)
    texto = re.sub(r'\n\|[\s|]*\|\n', '\n', texto)
    return texto.strip()


# — Classificação de peças —
TIPOS = [
    ("AUTUAÇÃO", ["autuação", "autuo o(a) presente"]),
    ("PORTARIA", ["portaria", "resolve:", "instaurar inquérito"]),
    ("DENÚNCIA", ["oferece a presente den", "denuncia como incurso"]),
    ("SENTENÇA", ["vistos, etc", "julgo procedente", "julgo improcedente", "condeno o r", "absolvo o r"]),
    ("PRONÚNCIA", ["pronuncio o r", "pronuncia o r"]),
    ("ALEGAÇÕES", ["alegações finais", "memoriais"]),
    ("RESPOSTA", ["resposta à acusação", "defesa prévia"]),
    ("RECURSO", ["apelação", "razões recursais", "contrarrazões"]),
    ("BO", ["boletim de ocorrência", "dados do registro", "relato/histórico"]),
    ("DECLARAÇÃO", ["termo de declarações", "às perguntas do(a) delegado"]),
    ("INTERROGATÓRIO", ["termo de qualificação e interrogatório"]),
    ("RELATÓRIO", ["relatório final", "dos fatos e circunstâncias apuradas"]),
    ("MPU", ["pedido de medida protetiva", "medida(s) protetiva(s) de urgência"]),
    ("RISCO", ["formulário nacional de avaliação de risco"]),
    ("LAUDO", ["laudo de exame", "lesões corporais", "exame médico pericial"]),
    ("DECISÃO", ["decido que", "defiro o pedido", "indefiro o pedido"]),
    ("DESPACHO", ["despacho", "cite-se", "intime-se", "cumpra-se"]),
    ("ATA", ["ata de audiência", "aberta a audiência"]),
    ("OFÍCIO", ["ofício nº", "oficio nº"]),
    ("CARTA PRECATÓRIA", ["carta precatória"]),
    ("BIC", ["boletim de informação criminal"]),
    ("CERTIDÃO", ["certifico que", "certidão", "certidão de publicação"]),
    ("INTIMAÇÃO", ["intimação", "fica intimado"]),
    ("MANDADO", ["mandado de"]),
    ("ALVARÁ", ["alvará de soltura"]),
    ("CONCLUSOS", ["autos conclusos"]),
    ("REMESSA", ["remessa", "faço a remessa"]),
    ("RECIBO", ["recibo de entrega"]),
    ("PETIÇÃO", ["petição ministerial", "petição", "registrar ciência"]),
    ("ASSINATURA", ["gerado por sinesp"]),
]

COMPLETAS = {"AUTUAÇÃO","PORTARIA","DENÚNCIA","SENTENÇA","PRONÚNCIA","ALEGAÇÕES",
             "RESPOSTA","RECURSO","BO","DECLARAÇÃO","INTERROGATÓRIO","RELATÓRIO",
             "MPU","RISCO","LAUDO","DECISÃO","DESPACHO","ATA","CARTA PRECATÓRIA","PETIÇÃO"}
RESUMO = {"OFÍCIO","BIC","CERTIDÃO","INTIMAÇÃO","MANDADO","ALVARÁ","CONCLUSOS","REMESSA","RECIBO"}
DESCARTE = {"ASSINATURA"}

def classificar(texto):
    t = texto.lower()[:2000]
    for tipo, kws in TIPOS:
        if any(kw in t for kw in kws): return tipo
    return "DOC"

def primeira_linha(texto, n=120):
    for l in texto.split('\n'):
        l = l.strip().strip('#').strip('*').strip()
        if len(l) > 10: return l[:n]
    return texto[:n]

def extrair_numero(nome):
    m = re.search(r'(\d{7}[-.]?\d{2})[_.](\d{4})[_.](\d{1,2})[_.](\d{2})[_.](\d{4})', nome)
    if m:
        p1 = m.group(1)
        if '-' not in p1 and '.' not in p1: p1 = p1[:7] + '-' + p1[7:]
        return f"{p1}.{m.group(2)}.{m.group(3)}.{m.group(4)}.{m.group(5)}"
    return Path(nome).stem

def extrair_meta_capa(txt):
    meta = {"classe": "", "assunto": ""}
    m = re.search(r'Classe:\s*\*?\*?([^\n*]+)', txt)
    if m: meta["classe"] = m.group(1).strip()
    m = re.search(r'Assuntos?:\s*\*?\*?([^\n*]+)', txt)
    if m: meta["assunto"] = m.group(1).strip()
    return meta

def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for blk in iter(lambda: f.read(8192), b''): h.update(blk)
    return h.hexdigest()


# — Pipeline —
def processar_pdf(pdf_path, prog=None):
    """PDF → Markdown com IDs PJe em cada peça."""
    import pymupdf4llm, pymupdf

    nome = os.path.basename(pdf_path)
    numero = extrair_numero(nome)
    doc = pymupdf.open(pdf_path); n_pags = len(doc); doc.close()

    if prog:
        pct = (prog.atual - 1) / prog.total * 100
        print(f"\n[{prog.atual}/{prog.total}] ({pct:.1f}%) {nome} — {n_pags} págs")

    # Tenta com layout (melhor qualidade). Se ONNX falhar, desativa e retenta.
    try:
        chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)
    except Exception:
        try:
            pymupdf4llm.use_layout(False)
            chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)
        except Exception as e:
            return {"numero": numero, "arquivo": nome, "status": "ERRO", "erro": str(e)}

    chars_bruto = sum(len(c['text']) for c in chunks)
    meta = extrair_meta_capa(chunks[0]['text'] if chunks else "")

    # Capturar doc_id ANTES de limpar, depois limpar e classificar
    pecas = []
    for i, c in enumerate(chunks):
        doc_id = extrair_doc_id(c['text'])
        txt = limpar(c['text'])
        if len(txt) < 30: continue
        tipo = classificar(txt)
        if tipo in DESCARTE: continue
        pecas.append({"pag": i+1, "tipo": tipo, "texto": txt, "doc_id": doc_id})

    # Agrupar páginas consecutivas do mesmo tipo
    grupos = []
    for p in pecas:
        if grupos and grupos[-1]["tipo"] == p["tipo"]:
            grupos[-1]["pag_fim"] = p["pag"]
            grupos[-1]["texto"] += "\n\n" + p["texto"]
            if p["doc_id"]: grupos[-1]["doc_ids"].append(p["doc_id"])
        else:
            grupos.append({
                "tipo": p["tipo"], "pag_ini": p["pag"], "pag_fim": p["pag"],
                "texto": p["texto"],
                "doc_ids": [p["doc_id"]] if p["doc_id"] else [],
            })

    md_text = _gerar_markdown(numero, meta, n_pags, grupos)
    nome_saida = numero.replace('.', '_').replace('-', '_') + ".md"
    (DIR_SAIDA / nome_saida).write_text(md_text, encoding='utf-8')

    r = {"numero": numero, "arquivo": nome, "arquivo_saida": nome_saida,
         "total_paginas": n_pags, "classe": meta["classe"], "assunto": meta["assunto"],
         "pecas": len(grupos), "chars_bruto": chars_bruto, "chars_limpo": len(md_text),
         "tokens_aprox": len(md_text) // 4,
         "reducao_pct": (1 - len(md_text) / chars_bruto) * 100 if chars_bruto > 0 else 0,
         "md5": md5(pdf_path), "status": "OK"}
    if prog: print(f"  -> {r['tokens_aprox']:,} tok | {r['pecas']} pecas | -{r['reducao_pct']:.0f}%")
    return r


def _fmt_ids(doc_ids):
    """'Num. 440866922 - Pág. 1, Num. 440866922 - Pág. 2'"""
    if not doc_ids: return ""
    return ", ".join(f"Num. {n} - Pág. {p}" for n, p in doc_ids)

def _gerar_markdown(numero, meta, n_pags, pecas):
    md = [f"# {numero}"]
    info = [x for x in [meta["classe"], meta["assunto"], f"{n_pags} págs"] if x]
    md.append(" | ".join(info)); md.append("")

    resumos = []
    for g in pecas:
        pags = f"p.{g['pag_ini']}" if g['pag_ini'] == g['pag_fim'] else f"p.{g['pag_ini']}-{g['pag_fim']}"
        ids = _fmt_ids(g["doc_ids"])

        if g["tipo"] in COMPLETAS or g["tipo"] == "DOC":
            if resumos:
                md.append("## Peças Secundárias"); md.extend(resumos); md.append(""); resumos = []
            h = f"## {g['tipo']} ({pags})"
            if ids: h += f" [{ids}]"
            md.append(h); md.append(""); md.append(g["texto"]); md.append("")

        elif g["tipo"] in RESUMO:
            entry = f"- **{g['tipo']}** {pags}"
            if ids: entry += f" [{ids}]"
            entry += f": {primeira_linha(g['texto'])}"
            resumos.append(entry)

    if resumos:
        md.append("## Peças Secundárias"); md.extend(resumos); md.append("")
    return "\n".join(md)


# — Main —
def main():
    print(f"\n{'=' * 60}\n  EXTRAÇÃO — PJe/TJBA (pymupdf4llm)\n{'=' * 60}")
    try:
        import pymupdf4llm; print("  [OK] pymupdf4llm")
    except ImportError: print("  [XX] pip install pymupdf4llm"); sys.exit(1)

    if not DIR_PDFS.exists() or not list(DIR_PDFS.glob("*.pdf")):
        print(f"\n  Nenhum PDF em '{DIR_PDFS}/'"); sys.exit(1)

    cache = json.loads(MAPEAMENTO_PATH.read_text(encoding='utf-8')) if MAPEAMENTO_PATH.exists() else {}
    pdfs = sorted(DIR_PDFS.glob("*.pdf")); total = len(pdfs)
    print(f"  {total} PDFs\n  {'─' * 55}")

    class Prog:
        def __init__(s): s.total = total; s.atual = 0
    prog = Prog()
    resultados = []; tokens = erros = pulados = 0; t0 = time.time()

    for i, pdf in enumerate(pdfs, 1):
        prog.atual = i; numero = extrair_numero(pdf.name); h = md5(str(pdf))
        if numero in cache and cache[numero].get("md5") == h:
            saida = DIR_SAIDA / cache[numero].get("md", "")
            if saida.exists():
                pulados += 1; tokens += cache[numero].get("tokens", 0)
                print(f"\n[{i}/{total}] CACHE {pdf.name}")
                resultados.append({"numero": numero, "arquivo": pdf.name, "arquivo_saida": cache[numero]["md"],
                    "tokens_aprox": cache[numero].get("tokens",0), "md5": h, "status": "CACHE"})
                continue
        try:
            r = processar_pdf(str(pdf), prog); resultados.append(r)
            if r["status"] == "OK": tokens += r["tokens_aprox"]
            else: erros += 1
        except Exception as e:
            erros += 1; print(f"\n  ERRO {pdf.name}: {e}")
            resultados.append({"numero": numero, "arquivo": pdf.name, "status": "ERRO", "erro": str(e)})

    ok = sum(1 for r in resultados if r["status"] in ("OK", "CACHE"))
    mapa = {r["numero"]: {"md": r.get("arquivo_saida",""), "tokens": r.get("tokens_aprox",0), "md5": r.get("md5","")}
            for r in resultados if r["status"] in ("OK", "CACHE")}
    MAPEAMENTO_PATH.write_text(json.dumps(mapa, ensure_ascii=False, indent=2), encoding='utf-8')
    RELATORIO_PATH.write_text(json.dumps({"total": total, "ok": ok, "erros": erros, "pulados": pulados,
        "tokens": tokens, "processos": resultados}, ensure_ascii=False, indent=2), encoding='utf-8')
    dt = time.time() - t0; m, s = divmod(int(dt), 60)
    print(f"\n\n  {'=' * 55}\n  {total} PDFs ({ok} ok, {erros} erros, {pulados} cache)\n  {tokens:,} tokens | {m}m{s:02d}s\n  {'=' * 55}\n")

if __name__ == "__main__":
    main()
