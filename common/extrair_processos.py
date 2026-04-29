#!/usr/bin/env python3
"""
PDF → Markdown otimizado para LLM.

Pipeline: extração (pymupdf4llm) → captura de IDs PJe → limpeza →
classificação de peças → detecção de sinalizadores → markdown compacto.

"""

import os
import sys
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime

# Garante que o pacote utils seja importável quando rodando direto
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


# ═══════════════════════════════════════════════════════════════════
#  Caminhos do projeto
# ═══════════════════════════════════════════════════════════════════

DIR_PDFS = Path(__file__).parent.parent / "pdfs"
DIR_SAIDA = Path(__file__).parent.parent / "textos_extraidos"
RELATORIO_PATH = Path(__file__).parent.parent / "relatorio_extracao.json"
MAPEAMENTO_PATH = Path(__file__).parent.parent / "mapeamento_processos.json"
DIR_SAIDA.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════════════
#  Helpers locais (específicos deste pipeline)
# ═══════════════════════════════════════════════════════════════════

def _md5_arquivo(path: str) -> str:
    """Hash MD5 para cache de PDFs já processados."""
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for bloco in iter(lambda: f.read(8192), b''):
            h.update(bloco)
    return h.hexdigest()


def _extrair_meta_capa(texto_primeira_pag: str) -> dict:
    """Extrai classe e assunto da primeira página (capa do PJe)."""
    import re
    meta = {"classe": "", "assunto": ""}
    m = re.search(r'Classe:\s*\*?\*?([^\n*]+)', texto_primeira_pag)
    if m:
        meta["classe"] = m.group(1).strip()
    m = re.search(r'Assuntos?:\s*\*?\*?([^\n*]+)', texto_primeira_pag)
    if m:
        meta["assunto"] = m.group(1).strip()
    return meta


# ═══════════════════════════════════════════════════════════════════
#  Pipeline principal
# ═══════════════════════════════════════════════════════════════════

def processar_pdf(pdf_path: str, prog=None) -> dict:
    """
    Processa um PDF do PJe e gera markdown otimizado.

    Pipeline:
      1. Abre o PDF e extrai chunks por página (pymupdf4llm)
      2. Para cada chunk: captura doc_id ANTES de limpar
      3. Limpa lixo institucional
      4. Classifica como peça
      5. Agrupa páginas consecutivas do mesmo tipo
      6. Detecta sinalizadores (cautelares, dados pessoais)
      7. Gera markdown final
    """
    import pymupdf4llm
    import pymupdf

    nome = os.path.basename(pdf_path)
    numero = extrair_numero_processo(nome)

    doc = pymupdf.open(pdf_path)
    n_paginas = len(doc)
    doc.close()

    if prog:
        pct = (prog.atual - 1) / prog.total * 100
        print(f"\n[{prog.atual}/{prog.total}] ({pct:.1f}%) {nome} — {n_paginas} págs")

    # Tenta com layout (melhor qualidade); se ONNX falhar, desativa
    try:
        chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)
    except Exception:
        try:
            pymupdf4llm.use_layout(False)
            chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)
        except Exception as e:
            return {
                "numero": numero,
                "arquivo": nome,
                "status": "ERRO",
                "erro": str(e),
            }

    chars_bruto = sum(len(c['text']) for c in chunks)
    meta = _extrair_meta_capa(chunks[0]['text'] if chunks else "")
    texto_completo = "\n".join(c['text'] for c in chunks)

    # ── Captura doc_id ANTES de limpar, depois classifica ──
    pecas = []
    for i, chunk in enumerate(chunks):
        doc_id = extrair_doc_id(chunk['text'])
        texto_limpo = limpar_texto(chunk['text'])
        if len(texto_limpo) < 30:
            continue
        tipo = classificar_peca(texto_limpo)
        if tipo in PECAS_DESCARTE:
            continue
        pecas.append({
            "pag": i + 1,
            "tipo": tipo,
            "texto": texto_limpo,
            "doc_id": doc_id,
        })

    # ── Agrupa páginas consecutivas do mesmo tipo ──
    grupos = []
    for p in pecas:
        if grupos and grupos[-1]["tipo"] == p["tipo"]:
            grupos[-1]["pag_fim"] = p["pag"]
            grupos[-1]["texto"] += "\n\n" + p["texto"]
            if p["doc_id"]:
                grupos[-1]["doc_ids"].append(p["doc_id"])
        else:
            grupos.append({
                "tipo": p["tipo"],
                "pag_ini": p["pag"],
                "pag_fim": p["pag"],
                "texto": p["texto"],
                "doc_ids": [p["doc_id"]] if p["doc_id"] else [],
            })

    # ── Detecta sinalizadores (cautelares, dados pessoais) ──
    sinalizadores = detectar_sinalizadores_processuais(grupos)
    dados_detectados = detectar_dados_pessoais(texto_completo)

    # ── Gera markdown final ──
    md_text = _gerar_markdown(
        numero, meta, n_paginas, grupos, sinalizadores, dados_detectados
    )
    nome_saida = numero.replace('.', '_').replace('-', '_') + ".md"
    (DIR_SAIDA / nome_saida).write_text(md_text, encoding='utf-8')

    # ── Resultado ──
    resultado = {
        "numero": numero,
        "arquivo": nome,
        "arquivo_saida": nome_saida,
        "total_paginas": n_paginas,
        "classe": meta["classe"],
        "assunto": meta["assunto"],
        "pecas": len(grupos),
        "chars_bruto": chars_bruto,
        "chars_limpo": len(md_text),
        "tokens_aprox": len(md_text) // 4,
        "reducao_pct": (
            (1 - len(md_text) / chars_bruto) * 100 if chars_bruto > 0 else 0
        ),
        "md5": _md5_arquivo(pdf_path),
        "status": "OK",
        "fase_aparente": sinalizadores["fase_aparente"],
        "provavel_status_cautelar": sinalizadores["provavel_status_cautelar"],
    }
    if prog:
        print(
            f"  -> {resultado['tokens_aprox']:,} tok | "
            f"{resultado['pecas']} pecas | "
            f"-{resultado['reducao_pct']:.0f}% | "
            f"{sinalizadores['fase_aparente']}"
        )
    return resultado


# ═══════════════════════════════════════════════════════════════════
#  Geração do markdown final
# ═══════════════════════════════════════════════════════════════════

def _gerar_markdown(
    numero: str,
    meta: dict,
    n_paginas: int,
    pecas: list,
    sinalizadores: dict,
    dados_detectados: dict,
) -> str:
    """
    Monta o markdown final com:
      - Cabeçalho (número, classe, assunto, páginas)
      - Bloco DADOS DETECTADOS (CPFs, telefones, datas, etc.)
      - Bloco SINALIZADORES PROCESSUAIS (cautelar, fase)
      - Peças completas em sequência
      - Peças resumidas em bloco final
    """
    md = [f"# {numero}"]
    info = [x for x in [meta["classe"], meta["assunto"], f"{n_paginas} págs"] if x]
    md.append(" | ".join(info))
    md.append("")

    # ── Bloco SINALIZADORES (alto valor para o Claude) ──
    md.append("## SINALIZADORES PROCESSUAIS (extração automática)")
    md.append(f"- **Fase aparente**: {sinalizadores['fase_aparente']}")
    md.append(
        f"- **Provável status da cautelar de comparecimento**: "
        f"{sinalizadores['provavel_status_cautelar']}"
    )
    eventos = sinalizadores["eventos"]
    flags_relevantes = [
        ("Audiência de custódia", eventos["tem_audiencia_custodia"]),
        ("Liberdade provisória", eventos["tem_liberdade_provisoria"]),
        ("Cautelar Art. 319", eventos["tem_cautelar_319"]),
        ("Termo de compromisso", eventos["tem_termo_compromisso"]),
        ("Sursis processual", eventos["tem_sursis_processual"]),
        ("ANPP", eventos["tem_anpp"]),
        ("Transação penal", eventos["tem_transacao_penal"]),
        ("Revogação de cautelar", eventos["tem_revogacao"]),
        ("Preventiva decretada", eventos["tem_preventiva_decretada"]),
        ("Sentença", eventos["tem_sentenca"]),
        ("Trânsito em julgado", eventos["tem_transito_julgado"]),
        ("Extinção da punibilidade", eventos["tem_extincao_punibilidade"]),
    ]
    flags_ativas = [nome for nome, ativo in flags_relevantes if ativo]
    if flags_ativas:
        md.append(f"- **Eventos detectados**: {', '.join(flags_ativas)}")

    if eventos["eventos"]:
        md.append("- **Linha do tempo da cautelar**:")
        for ev in eventos["eventos"]:
            data = f" em {ev['data_detectada']}" if ev["data_detectada"] else ""
            ids = formatar_doc_ids(ev["doc_ids"])
            ids_str = f" [{ids}]" if ids else ""
            md.append(
                f"  - {ev['tipo']} (p.{ev['pagina']}{ids_str}){data}"
            )
    md.append("")

    # ── Bloco DADOS DETECTADOS (auxilia extração de réus) ──
    md.append("## DADOS PESSOAIS DETECTADOS (extração automática — verificar papel)")
    if dados_detectados["cpfs"]:
        md.append(f"- **CPFs encontrados**: {', '.join(dados_detectados['cpfs'][:10])}")
    if dados_detectados["rgs"]:
        md.append(f"- **RGs encontrados**: {', '.join(dados_detectados['rgs'][:5])}")
    if dados_detectados["telefones"]:
        md.append(
            f"- **Telefones**: {', '.join(dados_detectados['telefones'][:5])}"
        )
    if dados_detectados["ceps"]:
        md.append(f"- **CEPs**: {', '.join(dados_detectados['ceps'][:5])}")
    if dados_detectados["datas"]:
        md.append(
            f"- **Datas relevantes**: {', '.join(dados_detectados['datas'][:10])}"
        )
    md.append(
        "> ⚠️ Estes dados podem incluir réu, vítima e testemunhas. "
        "Verificar o papel processual no texto antes de cadastrar."
    )
    md.append("")

    # ── Peças completas e resumidas ──
    resumos = []
    for grupo in pecas:
        if grupo['pag_ini'] == grupo['pag_fim']:
            pags = f"p.{grupo['pag_ini']}"
        else:
            pags = f"p.{grupo['pag_ini']}-{grupo['pag_fim']}"
        ids = formatar_doc_ids(grupo["doc_ids"])

        if grupo["tipo"] in PECAS_COMPLETAS or grupo["tipo"] == "DOC":
            # Despeja resumos pendentes antes de uma peça completa
            if resumos:
                md.append("## Peças Secundárias")
                md.extend(resumos)
                md.append("")
                resumos = []
            cabecalho = f"## {grupo['tipo']} ({pags})"
            if ids:
                cabecalho += f" [{ids}]"
            md.append(cabecalho)
            md.append("")
            md.append(grupo["texto"])
            md.append("")

        elif grupo["tipo"] in PECAS_RESUMO:
            entry = f"- **{grupo['tipo']}** {pags}"
            if ids:
                entry += f" [{ids}]"
            entry += f": {primeira_linha(grupo['texto'])}"
            resumos.append(entry)

    if resumos:
        md.append("## Peças Secundárias")
        md.extend(resumos)
        md.append("")

    return "\n".join(md)


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

    if not DIR_PDFS.exists() or not list(DIR_PDFS.glob("*.pdf")):
        print(f"\n  Nenhum PDF em '{DIR_PDFS}/'")
        sys.exit(1)

    cache = (
        json.loads(MAPEAMENTO_PATH.read_text(encoding='utf-8'))
        if MAPEAMENTO_PATH.exists() else {}
    )
    pdfs = sorted(DIR_PDFS.glob("*.pdf"))
    total = len(pdfs)
    print(f"  {total} PDFs\n  {'─' * 55}")

    class Progresso:
        def __init__(self):
            self.total = total
            self.atual = 0
    prog = Progresso()

    resultados = []
    tokens_total = erros = pulados = 0
    t_inicio = time.time()

    for i, pdf in enumerate(pdfs, 1):
        prog.atual = i
        numero = extrair_numero_processo(pdf.name)
        hash_atual = _md5_arquivo(str(pdf))

        # ── Cache hit ──
        if numero in cache and cache[numero].get("md5") == hash_atual:
            saida = DIR_SAIDA / cache[numero].get("md", "")
            if saida.exists():
                pulados += 1
                tokens_total += cache[numero].get("tokens", 0)
                print(f"\n[{i}/{total}] CACHE {pdf.name}")
                resultados.append({
                    "numero": numero,
                    "arquivo": pdf.name,
                    "arquivo_saida": cache[numero]["md"],
                    "tokens_aprox": cache[numero].get("tokens", 0),
                    "md5": hash_atual,
                    "status": "CACHE",
                })
                continue

        # ── Processamento ──
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
                "numero": numero,
                "arquivo": pdf.name,
                "status": "ERRO",
                "erro": str(e),
            })

    # ── Persiste cache e relatório ──
    ok = sum(1 for r in resultados if r["status"] in ("OK", "CACHE"))
    mapa = {
        r["numero"]: {
            "md": r.get("arquivo_saida", ""),
            "tokens": r.get("tokens_aprox", 0),
            "md5": r.get("md5", ""),
        }
        for r in resultados if r["status"] in ("OK", "CACHE")
    }
    MAPEAMENTO_PATH.write_text(
        json.dumps(mapa, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    RELATORIO_PATH.write_text(
        json.dumps(
            {
                "total": total,
                "ok": ok,
                "erros": erros,
                "pulados": pulados,
                "tokens": tokens_total,
                "processos": resultados,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
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
