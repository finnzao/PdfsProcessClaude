#!/usr/bin/env python3
"""
PDF → Markdown otimizado para LLM — PJe/TJBA.

Pipeline: extração (pymupdf4llm) → OCR fallback → captura de IDs PJe →
limpeza → classificação com confiança → agrupamento inteligente →
extração de partes e movimentação → detecção de sinalizadores → markdown compacto.
"""

import io
import os
import re
import sys
import json
import time
import inspect
import hashlib
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import (
    extrair_doc_id,
    limpar_texto,
    classificar_peca,
    PECAS_COMPLETAS,
    PECAS_RESUMO,
    PECAS_DESCARTE,
    detectar_dados_pessoais,
    detectar_sinalizadores_processuais,
    extrair_numero_processo,
    primeira_linha,
    formatar_doc_ids,
)
import utils as _utils_module


# ═══════════════════════════════════════════════════════════════════
#  Caminhos do projeto
# ═══════════════════════════════════════════════════════════════════

DIR_PDFS      = Path(__file__).parent.parent / "pdfs"
DIR_SAIDA     = Path(__file__).parent.parent / "textos_extraidos"
RELATORIO_PATH  = Path(__file__).parent.parent / "relatorio_extracao.json"
MAPEAMENTO_PATH = Path(__file__).parent.parent / "mapeamento_processos.json"
DIR_SAIDA.mkdir(exist_ok=True)

# Limiar de chars por página abaixo do qual tentamos OCR
OCR_CHAR_THRESHOLD = 80

# Papéis processuais e seus marcadores textuais
_PAPEIS_MARCADORES: dict[str, list[str]] = {
    "reu":        ["Réu:", "Acusado:", "Indiciado:", "Autuado:"],
    "vitima":     ["Vítima:", "Ofendido:", "Ofendida:"],
    "testemunha": ["Testemunha:", "Test.:"],
    "advogado":   ["Advogado:", "Advogada:", "Defensor:", "Defensora:"],
    "promotor":   ["Promotor:", "Promotora:", "MP:"],
}


# ═══════════════════════════════════════════════════════════════════
#  Cache helpers
# ═══════════════════════════════════════════════════════════════════

def _md5_arquivo(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(8192), b""):
            h.update(bloco)
    return h.hexdigest()


def _hash_utils() -> str:
    """Hash do código-fonte de utils para invalidar cache quando regras mudam."""
    src = inspect.getsource(_utils_module)
    return hashlib.md5(src.encode()).hexdigest()[:8]


def _cache_key(pdf_path: str) -> str:
    return f"{_md5_arquivo(pdf_path)}_{_hash_utils()}"


# ═══════════════════════════════════════════════════════════════════
#  OCR fallback
# ═══════════════════════════════════════════════════════════════════

def _pagina_precisa_ocr(chunk: dict) -> bool:
    texto = chunk.get("text", "")
    tem_imagem = bool(chunk.get("images"))
    return len(texto.strip()) < OCR_CHAR_THRESHOLD and tem_imagem


def _ocr_pagina(pdf_path: str, pagina_idx: int) -> str:
    """OCR de página específica via pytesseract (fallback silencioso se ausente)."""
    try:
        import fitz
        import pytesseract
        from PIL import Image

        doc = fitz.open(pdf_path)
        pix = doc[pagina_idx].get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(img, lang="por")
    except ImportError:
        return ""
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════
#  Classificador com score de confiança
# ═══════════════════════════════════════════════════════════════════

def _classificar_com_confianca(texto: str) -> tuple[str, float]:
    """
    Retorna (tipo, confiança 0.0–1.0).
    Confiança baixa (<0.3) rebaixa peças 'completas' para DOC.
    """
    tipo = classificar_peca(texto)
    if tipo == "DOC":
        return tipo, 0.0

    texto_lower = texto[:3000].lower()
    # Conta quantas keywords do tipo bateram (requer acesso a TIPOS_PECAS em utils)
    tipos_config = getattr(_utils_module, "TIPOS_PECAS", {})
    config = tipos_config.get(tipo, {})
    keywords = config.get("keywords", [])
    if not keywords:
        return tipo, 0.5  # sem config → confiança média

    hits = sum(1 for kw in keywords if kw.lower() in texto_lower)
    confianca = min(hits / len(keywords) * 3, 1.0)
    return tipo, confianca


# ═══════════════════════════════════════════════════════════════════
#  Agrupamento inteligente de páginas
# ═══════════════════════════════════════════════════════════════════

def _deve_agrupar(ultimo: dict, atual: dict) -> bool:
    """
    Agrupa apenas se: mesmo tipo + páginas contínuas + doc_ids compatíveis.
    Evita fundir duas decisões distintas do mesmo tipo.
    """
    if ultimo["tipo"] != atual["tipo"]:
        return False
    if atual["pag"] - ultimo["pag_fim"] > 1:
        return False
    # Se ambos têm doc_id explícito e são diferentes → peças distintas
    if ultimo["doc_ids"] and atual["doc_id"]:
        return atual["doc_id"] in ultimo["doc_ids"]
    return True


# ═══════════════════════════════════════════════════════════════════
#  Extração de metadados da capa
# ═══════════════════════════════════════════════════════════════════

def _extrair_meta_capa(texto: str) -> dict:
    meta = {"classe": "", "assunto": ""}
    m = re.search(r"Classe:\s*\*?\*?([^\n*]+)", texto)
    if m:
        meta["classe"] = m.group(1).strip()
    m = re.search(r"Assuntos?:\s*\*?\*?([^\n*]+)", texto)
    if m:
        meta["assunto"] = m.group(1).strip()
    return meta


# ═══════════════════════════════════════════════════════════════════
#  Extração de movimentação processual
# ═══════════════════════════════════════════════════════════════════

def _extrair_movimentacao(texto_capa: str) -> list[dict]:
    """
    Extrai linhas de movimentação do PJe.
    Formato típico: '15/03/2024  Conclusos para decisão'
    """
    pattern = re.compile(
        r"(\d{2}/\d{2}/\d{4})\s{1,10}([^\n]{10,120})",
        re.MULTILINE,
    )
    return [
        {"data": m.group(1), "descricao": m.group(2).strip()}
        for m in pattern.finditer(texto_capa)
    ]


# ═══════════════════════════════════════════════════════════════════
#  Extração de partes processuais
# ═══════════════════════════════════════════════════════════════════

_RE_CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
_RE_NOME = re.compile(r"[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][a-záéíóúâêîôûãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][a-záéíóúâêîôûãõç]+){1,6}")


def _extrair_partes(texto: str) -> list[dict]:
    """
    Detecta partes processuais com papel, nome e CPF quando disponível.
    Captura até 300 chars após o marcador para buscar CPF próximo.
    """
    partes: list[dict] = []
    for papel, marcadores in _PAPEIS_MARCADORES.items():
        for marcador in marcadores:
            for m in re.finditer(re.escape(marcador), texto, re.IGNORECASE):
                trecho = texto[m.end(): m.end() + 300]
                nome_m = _RE_NOME.search(trecho)
                cpf_m  = _RE_CPF.search(trecho)
                if not nome_m:
                    continue
                partes.append({
                    "papel": papel,
                    "nome":  nome_m.group().strip(),
                    "cpf":   cpf_m.group() if cpf_m else None,
                })
    # Deduplica por nome
    vistos: set[str] = set()
    unicos = []
    for p in partes:
        if p["nome"] not in vistos:
            vistos.add(p["nome"])
            unicos.append(p)
    return unicos


# ═══════════════════════════════════════════════════════════════════
#  Log estruturado por PDF
# ═══════════════════════════════════════════════════════════════════

def _salvar_log(nome_saida: str, log: dict) -> None:
    log_path = DIR_SAIDA / nome_saida.replace(".md", ".log.json")
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════
#  Pipeline principal
# ═══════════════════════════════════════════════════════════════════

def processar_pdf(pdf_path: str, prog=None) -> dict:
    import pymupdf4llm
    import pymupdf

    nome   = os.path.basename(pdf_path)
    numero = extrair_numero_processo(nome)
    t0     = time.time()

    doc = pymupdf.open(pdf_path)
    n_paginas = len(doc)
    doc.close()

    if prog:
        pct = (prog.atual - 1) / prog.total * 100
        print(f"\n[{prog.atual}/{prog.total}] ({pct:.1f}%) {nome} — {n_paginas} págs")

    # ── Extração base ──
    try:
        chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)
    except Exception:
        try:
            pymupdf4llm.use_layout(False)
            chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)
        except Exception as e:
            return {"numero": numero, "arquivo": nome, "status": "ERRO", "erro": str(e)}

    chars_bruto   = sum(len(c["text"]) for c in chunks)
    meta          = _extrair_meta_capa(chunks[0]["text"] if chunks else "")
    movimentacao  = _extrair_movimentacao(chunks[0]["text"] if chunks else "")
    texto_completo = "\n".join(c["text"] for c in chunks)

    # ── Processa cada página: OCR fallback → limpeza → classificação ──
    pecas: list[dict] = []
    paginas_ocr = 0

    for i, chunk in enumerate(chunks):
        texto_raw = chunk["text"]

        if _pagina_precisa_ocr(chunk):
            texto_ocr = _ocr_pagina(pdf_path, i)
            if len(texto_ocr) > len(texto_raw):
                texto_raw = texto_ocr
                paginas_ocr += 1

        doc_id      = extrair_doc_id(texto_raw)
        texto_limpo = limpar_texto(texto_raw)

        if len(texto_limpo) < 30:
            continue

        tipo, confianca = _classificar_com_confianca(texto_limpo)

        # Confiança baixa → rebaixa para DOC (vai para resumo)
        if confianca < 0.3 and tipo in PECAS_COMPLETAS:
            tipo = "DOC"

        if tipo in PECAS_DESCARTE:
            continue

        pecas.append({
            "pag":       i + 1,
            "tipo":      tipo,
            "texto":     texto_limpo,
            "doc_id":    doc_id,
            "confianca": confianca,
        })

    # ── Agrupamento inteligente ──
    grupos: list[dict] = []
    for p in pecas:
        if grupos and _deve_agrupar(grupos[-1], p):
            grupos[-1]["pag_fim"]  = p["pag"]
            grupos[-1]["texto"]   += "\n\n" + p["texto"]
            grupos[-1]["confianca"] = min(grupos[-1]["confianca"], p["confianca"])
            if p["doc_id"]:
                grupos[-1]["doc_ids"].append(p["doc_id"])
        else:
            grupos.append({
                "tipo":      p["tipo"],
                "pag_ini":   p["pag"],
                "pag_fim":   p["pag"],
                "texto":     p["texto"],
                "doc_ids":   [p["doc_id"]] if p["doc_id"] else [],
                "confianca": p["confianca"],
            })

    # ── Enriquecimento ──
    sinalizadores   = detectar_sinalizadores_processuais(grupos)
    dados_detectados = detectar_dados_pessoais(texto_completo)
    partes          = _extrair_partes(texto_completo)

    # ── Geração do markdown ──
    md_text    = _gerar_markdown(numero, meta, n_paginas, grupos,
                                  sinalizadores, dados_detectados,
                                  partes, movimentacao)
    nome_saida = numero.replace(".", "_").replace("-", "_") + ".md"
    (DIR_SAIDA / nome_saida).write_text(md_text, encoding="utf-8")

    # ── Log estruturado ──
    _salvar_log(nome_saida, {
        "arquivo":      nome,
        "timestamp":    datetime.now().isoformat(),
        "paginas_total": n_paginas,
        "paginas_ocr":  paginas_ocr,
        "tempo_s":      round(time.time() - t0, 2),
        "pecas": [
            {"tipo": g["tipo"], "paginas": f"{g['pag_ini']}-{g['pag_fim']}",
             "confianca": round(g["confianca"], 2)}
            for g in grupos
        ],
        "partes": partes,
        "movimentacao_itens": len(movimentacao),
    })

    resultado = {
        "numero":                   numero,
        "arquivo":                  nome,
        "arquivo_saida":            nome_saida,
        "total_paginas":            n_paginas,
        "paginas_ocr":              paginas_ocr,
        "classe":                   meta["classe"],
        "assunto":                  meta["assunto"],
        "pecas":                    len(grupos),
        "partes_detectadas":        len(partes),
        "chars_bruto":              chars_bruto,
        "chars_limpo":              len(md_text),
        "tokens_aprox":             len(md_text) // 4,
        "reducao_pct":              (1 - len(md_text) / chars_bruto) * 100 if chars_bruto else 0,
        "cache_key":                _cache_key(pdf_path),
        "status":                   "OK",
        "fase_aparente":            sinalizadores["fase_aparente"],
        "provavel_status_cautelar": sinalizadores["provavel_status_cautelar"],
    }

    if prog:
        ocr_str = f" | {paginas_ocr} OCR" if paginas_ocr else ""
        print(
            f"  -> {resultado['tokens_aprox']:,} tok | "
            f"{resultado['pecas']} peças | "
            f"-{resultado['reducao_pct']:.0f}%"
            f"{ocr_str} | {sinalizadores['fase_aparente']}"
        )
    return resultado


# ═══════════════════════════════════════════════════════════════════
#  Geração do markdown — blocos independentes
# ═══════════════════════════════════════════════════════════════════

def _bloco_cabecalho(numero: str, meta: dict, n_paginas: int) -> list[str]:
    info = [x for x in [meta["classe"], meta["assunto"], f"{n_paginas} págs"] if x]
    return [f"# {numero}", " | ".join(info), ""]


def _bloco_movimentacao(movimentacao: list[dict]) -> list[str]:
    if not movimentacao:
        return []
    linhas = ["## MOVIMENTAÇÃO PROCESSUAL",
              "| Data | Descrição |", "|------|-----------|"]
    for mov in movimentacao:
        linhas.append(f"| {mov['data']} | {mov['descricao']} |")
    linhas.append("")
    return linhas


def _bloco_partes(partes: list[dict]) -> list[str]:
    if not partes:
        return []
    linhas = ["## PARTES PROCESSUAIS (extração automática — verificar papel)"]
    for p in partes:
        cpf_str = f" — CPF: {p['cpf']}" if p["cpf"] else ""
        linhas.append(f"- **{p['papel'].upper()}**: {p['nome']}{cpf_str}")
    linhas.append(
        "> ⚠️ Verificar papel processual no texto antes de cadastrar."
    )
    linhas.append("")
    return linhas


def _bloco_sinalizadores(sinalizadores: dict) -> list[str]:
    linhas = [
        "## SINALIZADORES PROCESSUAIS (extração automática)",
        f"- **Fase aparente**: {sinalizadores['fase_aparente']}",
        f"- **Provável status da cautelar de comparecimento**: "
        f"{sinalizadores['provavel_status_cautelar']}",
    ]
    eventos = sinalizadores["eventos"]
    flags_relevantes = [
        ("Audiência de custódia",    eventos["tem_audiencia_custodia"]),
        ("Liberdade provisória",     eventos["tem_liberdade_provisoria"]),
        ("Cautelar Art. 319",        eventos["tem_cautelar_319"]),
        ("Termo de compromisso",     eventos["tem_termo_compromisso"]),
        ("Sursis processual",        eventos["tem_sursis_processual"]),
        ("ANPP",                     eventos["tem_anpp"]),
        ("Transação penal",          eventos["tem_transacao_penal"]),
        ("Revogação de cautelar",    eventos["tem_revogacao"]),
        ("Preventiva decretada",     eventos["tem_preventiva_decretada"]),
        ("Sentença",                 eventos["tem_sentenca"]),
        ("Trânsito em julgado",      eventos["tem_transito_julgado"]),
        ("Extinção da punibilidade", eventos["tem_extincao_punibilidade"]),
    ]
    flags_ativas = [nome for nome, ativo in flags_relevantes if ativo]
    if flags_ativas:
        linhas.append(f"- **Eventos detectados**: {', '.join(flags_ativas)}")

    if eventos["eventos"]:
        linhas.append("- **Linha do tempo da cautelar**:")
        for ev in eventos["eventos"]:
            data    = f" em {ev['data_detectada']}" if ev["data_detectada"] else ""
            ids     = formatar_doc_ids(ev["doc_ids"])
            ids_str = f" [{ids}]" if ids else ""
            linhas.append(f"  - {ev['tipo']} (p.{ev['pagina']}{ids_str}){data}")

    linhas.append("")
    return linhas


def _bloco_dados_pessoais(dados: dict) -> list[str]:
    linhas = ["## DADOS PESSOAIS DETECTADOS (extração automática — verificar papel)"]
    if dados["cpfs"]:
        linhas.append(f"- **CPFs**: {', '.join(dados['cpfs'][:10])}")
    if dados["rgs"]:
        linhas.append(f"- **RGs**: {', '.join(dados['rgs'][:5])}")
    if dados["telefones"]:
        linhas.append(f"- **Telefones**: {', '.join(dados['telefones'][:5])}")
    if dados["ceps"]:
        linhas.append(f"- **CEPs**: {', '.join(dados['ceps'][:5])}")
    if dados["datas"]:
        linhas.append(f"- **Datas relevantes**: {', '.join(dados['datas'][:10])}")
    linhas.append(
        "> ⚠️ Estes dados podem incluir réu, vítima e testemunhas. "
        "Verificar o papel processual no texto antes de cadastrar."
    )
    linhas.append("")
    return linhas


def _bloco_pecas(grupos: list[dict]) -> list[str]:
    linhas: list[str] = []
    resumos: list[str] = []

    for grupo in grupos:
        pags = (
            f"p.{grupo['pag_ini']}"
            if grupo["pag_ini"] == grupo["pag_fim"]
            else f"p.{grupo['pag_ini']}-{grupo['pag_fim']}"
        )
        ids     = formatar_doc_ids(grupo["doc_ids"])
        ids_str = f" [{ids}]" if ids else ""
        conf    = grupo.get("confianca", 1.0)

        if grupo["tipo"] in PECAS_COMPLETAS or grupo["tipo"] == "DOC":
            if resumos:
                linhas += ["## Peças Secundárias"] + resumos + [""]
                resumos = []
            cab = f"## {grupo['tipo']} ({pags}){ids_str}"
            if conf < 0.5:
                cab += f"  <!-- confiança: {conf:.0%} -->"
            linhas += [cab, "", grupo["texto"], ""]

        elif grupo["tipo"] in PECAS_RESUMO:
            entry = f"- **{grupo['tipo']}** {pags}{ids_str}: {primeira_linha(grupo['texto'])}"
            resumos.append(entry)

    if resumos:
        linhas += ["## Peças Secundárias"] + resumos + [""]

    return linhas


def _gerar_markdown(
    numero: str,
    meta: dict,
    n_paginas: int,
    grupos: list[dict],
    sinalizadores: dict,
    dados_detectados: dict,
    partes: list[dict],
    movimentacao: list[dict],
) -> str:
    blocos = (
        _bloco_cabecalho(numero, meta, n_paginas)
        + _bloco_movimentacao(movimentacao)
        + _bloco_partes(partes)
        + _bloco_sinalizadores(sinalizadores)
        + _bloco_dados_pessoais(dados_detectados)
        + _bloco_pecas(grupos)
    )
    return "\n".join(blocos)


# ═══════════════════════════════════════════════════════════════════
#  Loop principal
# ═══════════════════════════════════════════════════════════════════

def main():
    print(f"\n{'=' * 60}\n  EXTRAÇÃO — PJe/TJBA (pymupdf4llm)\n{'=' * 60}")

    try:
        import pymupdf4llm  # noqa: F401
        print("  [OK] pymupdf4llm")
    except ImportError:
        print("  [XX] pip install pymupdf4llm")
        sys.exit(1)

    try:
        import pytesseract  # noqa: F401
        print("  [OK] pytesseract (OCR ativo)")
    except ImportError:
        print("  [--] pytesseract ausente — OCR desativado")

    if not DIR_PDFS.exists() or not list(DIR_PDFS.glob("*.pdf")):
        print(f"\n  Nenhum PDF em '{DIR_PDFS}/'")
        sys.exit(1)

    cache = (
        json.loads(MAPEAMENTO_PATH.read_text(encoding="utf-8"))
        if MAPEAMENTO_PATH.exists() else {}
    )
    pdfs  = sorted(DIR_PDFS.glob("*.pdf"))
    total = len(pdfs)
    print(f"  {total} PDFs\n  {'─' * 55}")

    class Progresso:
        def __init__(self):
            self.total = total
            self.atual = 0

    prog = Progresso()
    resultados: list[dict] = []
    tokens_total = erros = pulados = 0
    t_inicio = time.time()

    for i, pdf in enumerate(pdfs, 1):
        prog.atual = i
        numero     = extrair_numero_processo(pdf.name)
        ck_atual   = _cache_key(str(pdf))

        # ── Cache hit: valida PDF + versão das regras ──
        entrada_cache = cache.get(numero, {})
        if entrada_cache.get("cache_key") == ck_atual:
            saida = DIR_SAIDA / entrada_cache.get("md", "")
            if saida.exists():
                pulados      += 1
                tokens_total += entrada_cache.get("tokens", 0)
                print(f"\n[{i}/{total}] CACHE {pdf.name}")
                resultados.append({
                    "numero":        numero,
                    "arquivo":       pdf.name,
                    "arquivo_saida": entrada_cache["md"],
                    "tokens_aprox":  entrada_cache.get("tokens", 0),
                    "cache_key":     ck_atual,
                    "status":        "CACHE",
                })
                continue

        try:
            r = processar_pdf(str(pdf), prog)
            resultados.append(r)
            if r["status"] == "OK":
                tokens_total += r["tokens_aprox"]
            else:
                erros += 1
        except Exception as e:
            erros += 1
            print(f"\n  ERRO {pdf.name}: {e}")
            resultados.append({
                "numero":  numero,
                "arquivo": pdf.name,
                "status":  "ERRO",
                "erro":    str(e),
            })

    # ── Persiste cache e relatório ──
    ok = sum(1 for r in resultados if r["status"] in ("OK", "CACHE"))
    mapa = {
        r["numero"]: {
            "md":        r.get("arquivo_saida", ""),
            "tokens":    r.get("tokens_aprox", 0),
            "cache_key": r.get("cache_key", ""),
        }
        for r in resultados if r["status"] in ("OK", "CACHE")
    }
    MAPEAMENTO_PATH.write_text(
        json.dumps(mapa, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    RELATORIO_PATH.write_text(
        json.dumps(
            {"total": total, "ok": ok, "erros": erros, "pulados": pulados,
             "tokens": tokens_total, "processos": resultados},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    dt = time.time() - t_inicio
    m, s = divmod(int(dt), 60)
    print(
        f"\n\n  {'=' * 55}\n"
        f"  {total} PDFs ({ok} ok, {erros} erros, {pulados} cache)\n"
        f"  {tokens_total:,} tokens | {m}m{s:02d}s\n"
        f"  {'=' * 55}\n"
    )


if __name__ == "__main__":
    main()