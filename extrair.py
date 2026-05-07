#!/usr/bin/env python3
"""
extrair.py — CLI standalone para extracao de PDFs juridicos -> markdown.

Roda direto na raiz do projeto. Le PDFs de pdfs/ e gera markdowns em
textos_extraidos/, com cache invalidado por hash do conteudo + hash dos
modulos de utils.

Uso:
    python extrair.py                          # processa pdfs/ -> textos_extraidos/
    python extrair.py --src minha_pasta        # outra pasta de entrada
    python extrair.py --dst saida              # outra pasta de saida
    python extrair.py --workers 4              # paraleliza 4 PDFs simultaneos
    python extrair.py --force                  # ignora cache, reprocessa tudo
    python extrair.py --no-ocr                 # desabilita OCR
    python extrair.py --force-ocr              # OCR em todas as paginas
    python extrair.py --threshold 80           # chars/pag abaixo do qual aciona OCR
    python extrair.py --dry-run                # mostra o que faria, sem processar
    python extrair.py --status                 # status do cache
    python extrair.py --clean-cache            # limpa cache
    python extrair.py --only PADRAO            # processa apenas PDFs casando com glob
    python extrair.py --verbose                # logs detalhados por pagina

Exemplos:
    python extrair.py --workers 8 --force-ocr  # full reprocesso paralelo com OCR
    python extrair.py --only "8001*.pdf"       # so processos 8001*
    python extrair.py --dry-run                # ver fila antes de rodar
"""

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Garante que pacotes locais funcionem mesmo se o script for chamado de outro lugar
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.extrator_pdf import (
    DEFAULT_OCR_THRESHOLD,
    processar_pdf,
    cache_key_arquivo,
    versao_utils,
)
from common.utils_io import (
    ensure_dir,
    formato_tamanho,
    formato_tempo,
    ler_json,
    salvar_json,
)


# ========================================================
#   Caminhos default
# ========================================================
DIR_PDFS_DEFAULT = ROOT / "pdfs"
DIR_SAIDA_DEFAULT = ROOT / "textos_extraidos"
MAPEAMENTO_PATH = ROOT / "mapeamento_processos.json"
RELATORIO_PATH = ROOT / "relatorio_extracao.json"


# ========================================================
#   Helpers de UI no terminal
# ========================================================

class Cores:
    """Cores ANSI. Desabilitadas se o terminal nao suportar."""
    if sys.stdout.isatty() and os.name != "nt" or os.environ.get("FORCE_COLOR"):
        RESET = "\033[0m"
        BOLD = "\033[1m"
        DIM = "\033[2m"
        VERDE = "\033[32m"
        AMARELO = "\033[33m"
        VERMELHO = "\033[31m"
        AZUL = "\033[34m"
        CIANO = "\033[36m"
        MAGENTA = "\033[35m"
    else:
        RESET = BOLD = DIM = VERDE = AMARELO = VERMELHO = AZUL = CIANO = MAGENTA = ""


def banner():
    print()
    print(f"{Cores.BOLD}{Cores.CIANO}{'=' * 64}{Cores.RESET}")
    print(f"{Cores.BOLD}{Cores.CIANO}  EXTRATOR PDF -> MARKDOWN  |  PJe / TJBA{Cores.RESET}")
    print(f"{Cores.BOLD}{Cores.CIANO}{'=' * 64}{Cores.RESET}")


def progress_bar(atual, total, largura=40):
    if total == 0:
        return "[" + " " * largura + "]"
    pct = atual / total
    cheio = int(pct * largura)
    barra = "#" * cheio + "-" * (largura - cheio)
    return f"[{barra}] {pct * 100:5.1f}% ({atual}/{total})"


# ========================================================
#   Verificacao de dependencias
# ========================================================

def verificar_dependencias():
    """Checa pymupdf4llm (obrigatorio) e pytesseract (opcional)."""
    faltando = []
    try:
        import pymupdf4llm  # noqa: F401
        print(f"  {Cores.VERDE}[OK]{Cores.RESET} pymupdf4llm")
    except ImportError:
        faltando.append("pymupdf4llm")

    try:
        import pymupdf  # noqa: F401
        print(f"  {Cores.VERDE}[OK]{Cores.RESET} pymupdf")
    except ImportError:
        faltando.append("pymupdf")

    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        print(f"  {Cores.VERDE}[OK]{Cores.RESET} pytesseract + Pillow (OCR ativo)")
        ocr_disponivel = True
    except ImportError:
        print(f"  {Cores.AMARELO}[--]{Cores.RESET} pytesseract ausente — OCR desativado")
        ocr_disponivel = False

    if faltando:
        print(f"\n  {Cores.VERMELHO}Instale:{Cores.RESET} pip install {' '.join(faltando)}")
        sys.exit(1)

    return ocr_disponivel


# ========================================================
#   Cache management
# ========================================================

def carregar_cache():
    return ler_json(MAPEAMENTO_PATH, default={})


def salvar_cache(mapa):
    salvar_json(MAPEAMENTO_PATH, mapa)


def status_cache(dir_pdfs, dir_saida):
    """Mostra status atual do cache."""
    cache = carregar_cache()
    pdfs = list(dir_pdfs.glob("*.pdf")) if dir_pdfs.exists() else []
    mds = list(dir_saida.glob("*.md")) if dir_saida.exists() else []

    print(f"\n  {Cores.BOLD}Status do cache{Cores.RESET}")
    print(f"  {'-' * 50}")
    print(f"  PDFs em {dir_pdfs.name}/:           {len(pdfs)}")
    print(f"  Markdowns em {dir_saida.name}/:      {len(mds)}")
    print(f"  Entradas em mapeamento_processos:   {len(cache)}")
    print(f"  Versao atual de utils:              {versao_utils()}")

    if not cache:
        print(f"\n  {Cores.AMARELO}Cache vazio.{Cores.RESET}")
        return

    # Quantos estao com cache valido?
    validos = invalidos = orfaos = 0
    versao_atual = versao_utils()
    for entrada in cache.values():
        ck = entrada.get("cache_key", "")
        if not ck:
            invalidos += 1
            continue
        if not ck.endswith(versao_atual):
            invalidos += 1
        else:
            md_path = dir_saida / entrada.get("md", "")
            if md_path.exists():
                validos += 1
            else:
                orfaos += 1

    print(f"\n  Cache valido:           {Cores.VERDE}{validos}{Cores.RESET}")
    print(f"  Cache invalidado:       {Cores.AMARELO}{invalidos}{Cores.RESET} (versao utils mudou)")
    print(f"  Cache orfao:            {Cores.AMARELO}{orfaos}{Cores.RESET} (md deletado)")
    print()


def limpar_cache():
    if MAPEAMENTO_PATH.exists():
        MAPEAMENTO_PATH.unlink()
        print(f"  {Cores.VERDE}OK{Cores.RESET}  Cache limpo: {MAPEAMENTO_PATH.name}")
    else:
        print(f"  {Cores.AMARELO}Cache ja vazio.{Cores.RESET}")
    if RELATORIO_PATH.exists():
        RELATORIO_PATH.unlink()
        print(f"  {Cores.VERDE}OK{Cores.RESET}  Relatorio anterior removido.")


# ========================================================
#   Pipeline principal
# ========================================================

def listar_pdfs(dir_pdfs, padrao_glob=None):
    if not dir_pdfs.exists():
        return []
    if padrao_glob:
        return sorted(dir_pdfs.glob(padrao_glob))
    return sorted(dir_pdfs.glob("*.pdf"))


def filtrar_pendentes(pdfs, dir_saida, cache, force=False):
    """Separa pdfs em (precisa_processar, ja_em_cache)."""
    pendentes = []
    pulados = []
    versao_atual = versao_utils()

    for pdf in pdfs:
        ck = cache_key_arquivo(pdf)
        if force:
            pendentes.append(pdf)
            continue

        # Procura entrada do cache pelo numero CNJ deduzido do nome
        from common.utils_io import extrair_numero_processo
        numero = extrair_numero_processo(pdf.name)
        entrada = cache.get(numero, {})
        if entrada.get("cache_key") == ck:
            md_path = dir_saida / entrada.get("md", "")
            if md_path.exists():
                pulados.append((pdf, entrada))
                continue
        pendentes.append(pdf)

    return pendentes, pulados


def _executar_paralelo(pdfs, dir_saida, opts, n_workers):
    """Roda processar_pdf em paralelo com ProcessPoolExecutor."""
    resultados = []
    total = len(pdfs)

    print(f"\n  {Cores.BOLD}Processando {total} PDF(s) com {n_workers} worker(s){Cores.RESET}")
    print(f"  {'-' * 50}")

    t_inicio = time.time()
    feitos = 0

    with ProcessPoolExecutor(max_workers=n_workers) as exe:
        futures = {
            exe.submit(processar_pdf, str(p), str(dir_saida), opts): p
            for p in pdfs
        }
        for fut in as_completed(futures):
            pdf = futures[fut]
            feitos += 1
            try:
                r = fut.result()
                if r["status"] == "OK":
                    icon = f"{Cores.VERDE}OK{Cores.RESET}"
                    extra = f"{r['tokens_aprox']:>6,} tok | {r['pecas']:>3} pecas | -{r['reducao_pct']:.0f}%"
                    if r.get("paginas_ocr", 0):
                        extra += f" | {r['paginas_ocr']} OCR"
                else:
                    icon = f"{Cores.VERMELHO}ERRO{Cores.RESET}"
                    extra = r.get("erro", "?")[:50]
            except Exception as e:
                r = {"arquivo": pdf.name, "status": "ERRO", "erro": str(e), "numero": pdf.stem}
                icon = f"{Cores.VERMELHO}ERRO{Cores.RESET}"
                extra = str(e)[:50]
            resultados.append(r)

            # Progress bar
            barra = progress_bar(feitos, total, largura=24)
            print(f"  {barra} [{icon}] {pdf.name[:40]:<40}  {extra}")

    dt = time.time() - t_inicio
    return resultados, dt


def _executar_serial(pdfs, dir_saida, opts):
    """Versao serial — usada quando workers=1."""
    resultados = []
    total = len(pdfs)

    print(f"\n  {Cores.BOLD}Processando {total} PDF(s) (modo serial){Cores.RESET}")
    print(f"  {'-' * 50}")

    t_inicio = time.time()
    for i, pdf in enumerate(pdfs, 1):
        barra = progress_bar(i - 1, total, largura=24)
        print(f"\n  {barra}")
        print(f"  {Cores.DIM}[{i}/{total}]{Cores.RESET} {pdf.name}")
        try:
            r = processar_pdf(str(pdf), str(dir_saida), opts)
            if r["status"] == "OK":
                ocr = f" | {r['paginas_ocr']} OCR" if r.get("paginas_ocr") else ""
                print(f"  {Cores.VERDE}OK{Cores.RESET}  {r['tokens_aprox']:,} tok | "
                      f"{r['pecas']} pecas | -{r['reducao_pct']:.0f}%{ocr}")
            else:
                print(f"  {Cores.VERMELHO}ERRO{Cores.RESET} {r.get('erro', '?')}")
        except Exception as e:
            r = {"arquivo": pdf.name, "status": "ERRO", "erro": str(e), "numero": pdf.stem}
            print(f"  {Cores.VERMELHO}ERRO{Cores.RESET} {e}")
        resultados.append(r)

    dt = time.time() - t_inicio
    return resultados, dt


def main():
    parser = argparse.ArgumentParser(
        prog="extrair",
        description="Extrai PDFs juridicos para markdown otimizado para LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Exemplos:")[1] if "Exemplos:" in __doc__ else "",
    )
    parser.add_argument("--src", type=str, default=str(DIR_PDFS_DEFAULT),
                        help=f"pasta de PDFs (default: {DIR_PDFS_DEFAULT.name}/)")
    parser.add_argument("--dst", type=str, default=str(DIR_SAIDA_DEFAULT),
                        help=f"pasta de saida (default: {DIR_SAIDA_DEFAULT.name}/)")
    parser.add_argument("--workers", type=int, default=0,
                        help="processos paralelos (0=auto baseado em CPU)")
    parser.add_argument("--force", action="store_true",
                        help="ignora cache, reprocessa tudo")
    parser.add_argument("--no-ocr", action="store_true",
                        help="desabilita OCR")
    parser.add_argument("--force-ocr", action="store_true",
                        help="OCR em todas as paginas")
    parser.add_argument("--threshold", type=int, default=DEFAULT_OCR_THRESHOLD,
                        help=f"chars/pag para acionar OCR (default: {DEFAULT_OCR_THRESHOLD})")
    parser.add_argument("--dry-run", action="store_true",
                        help="mostra o que faria, sem processar")
    parser.add_argument("--status", action="store_true",
                        help="mostra status do cache e sai")
    parser.add_argument("--clean-cache", action="store_true",
                        help="limpa cache e sai")
    parser.add_argument("--only", type=str, default=None,
                        help="glob de filtragem (ex: '8001*.pdf')")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="logs detalhados por pagina")
    args = parser.parse_args()

    dir_pdfs = Path(args.src).resolve()
    dir_saida = Path(args.dst).resolve()
    ensure_dir(dir_saida)

    banner()

    # Comandos especiais
    if args.clean_cache:
        limpar_cache()
        return
    if args.status:
        status_cache(dir_pdfs, dir_saida)
        return

    print(f"  {Cores.BOLD}Configuracao{Cores.RESET}")
    print(f"  {'-' * 50}")
    print(f"  Entrada:    {dir_pdfs}")
    print(f"  Saida:      {dir_saida}")
    print(f"  Workers:    {args.workers if args.workers > 0 else 'auto'}")
    print(f"  OCR:        {'desabilitado' if args.no_ocr else ('forcado' if args.force_ocr else f'auto (threshold={args.threshold})')}")
    print(f"  Cache:      {'ignorado (--force)' if args.force else 'ativo'}")
    if args.only:
        print(f"  Filtro:     {args.only}")
    print()

    # Dependencias (pulado em --dry-run para permitir preview sem instalar)
    if not args.dry_run:
        print(f"  {Cores.BOLD}Verificando dependencias{Cores.RESET}")
        print(f"  {'-' * 50}")
        ocr_disponivel = verificar_dependencias()
    else:
        ocr_disponivel = False

    # Listagem
    pdfs = listar_pdfs(dir_pdfs, padrao_glob=args.only)
    if not pdfs:
        print(f"\n  {Cores.AMARELO}Nenhum PDF encontrado em {dir_pdfs}/{Cores.RESET}")
        if not dir_pdfs.exists():
            print(f"  Crie a pasta com: mkdir -p {dir_pdfs.relative_to(ROOT)}")
        return

    cache = carregar_cache()
    pendentes, pulados = filtrar_pendentes(pdfs, dir_saida, cache, force=args.force)

    print(f"\n  {Cores.BOLD}Inventario{Cores.RESET}")
    print(f"  {'-' * 50}")
    print(f"  Total de PDFs:     {len(pdfs)}")
    print(f"  Em cache valido:   {Cores.VERDE}{len(pulados)}{Cores.RESET}")
    print(f"  A processar:       {Cores.CIANO}{len(pendentes)}{Cores.RESET}")
    tamanho_total = sum(p.stat().st_size for p in pendentes)
    print(f"  Tamanho total:     {formato_tamanho(tamanho_total)}")

    if args.dry_run:
        print(f"\n  {Cores.BOLD}DRY-RUN — nada sera processado{Cores.RESET}")
        if pendentes:
            print(f"\n  {Cores.BOLD}Seriam processados:{Cores.RESET}")
            for p in pendentes[:20]:
                print(f"    {p.name}  ({formato_tamanho(p.stat().st_size)})")
            if len(pendentes) > 20:
                print(f"    ... +{len(pendentes) - 20} arquivos")
        if pulados:
            print(f"\n  {Cores.BOLD}Em cache (seriam pulados):{Cores.RESET}")
            for p, _ in pulados[:5]:
                print(f"    {p.name}")
            if len(pulados) > 5:
                print(f"    ... +{len(pulados) - 5} arquivos")
        return

    if not pendentes:
        print(f"\n  {Cores.VERDE}Tudo em cache. Nada a fazer.{Cores.RESET}")
        print(f"  Use --force para reprocessar tudo.\n")
        return

    # Determinar n_workers
    n_workers = args.workers
    if n_workers <= 0:
        n_cpu = os.cpu_count() or 4
        # Conservador: PDFs grandes consomem RAM. Cap em 4 para nao saturar.
        n_workers = max(1, min(n_cpu // 2, 4, len(pendentes)))

    # Opts comuns para todos os workers
    opts = {
        "use_ocr": not args.no_ocr and ocr_disponivel,
        "force_ocr": args.force_ocr and ocr_disponivel,
        "ocr_threshold": args.threshold,
        "verbose": args.verbose,
    }

    # Executar
    if n_workers <= 1 or len(pendentes) <= 1:
        resultados, dt = _executar_serial(pendentes, dir_saida, opts)
    else:
        resultados, dt = _executar_paralelo(pendentes, dir_saida, opts, n_workers)

    # Atualizar cache
    for r in resultados:
        if r.get("status") == "OK":
            cache[r["numero"]] = {
                "md": r.get("arquivo_saida", ""),
                "tokens": r.get("tokens_aprox", 0),
                "cache_key": r.get("cache_key", ""),
                "data": time.strftime("%Y-%m-%d %H:%M"),
            }
    salvar_cache(cache)

    # Adicionar entradas de cache aos resultados para o relatorio
    for pdf, entrada in pulados:
        from common.utils_io import extrair_numero_processo
        resultados.append({
            "arquivo": pdf.name,
            "numero": extrair_numero_processo(pdf.name),
            "arquivo_saida": entrada.get("md", ""),
            "tokens_aprox": entrada.get("tokens", 0),
            "cache_key": entrada.get("cache_key", ""),
            "status": "CACHE",
        })

    # Relatorio final
    ok = sum(1 for r in resultados if r["status"] == "OK")
    cached = sum(1 for r in resultados if r["status"] == "CACHE")
    erros = sum(1 for r in resultados if r["status"] == "ERRO")
    tokens = sum(r.get("tokens_aprox", 0) for r in resultados)

    salvar_json(RELATORIO_PATH, {
        "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tempo_s": round(dt, 2),
        "total": len(resultados),
        "ok": ok,
        "cache": cached,
        "erros": erros,
        "tokens_total": tokens,
        "config": opts,
        "processos": resultados,
    })

    print(f"\n  {Cores.BOLD}Concluido{Cores.RESET}")
    print(f"  {'-' * 50}")
    print(f"  Tempo:               {formato_tempo(dt)}")
    print(f"  Processados agora:   {Cores.VERDE}{ok}{Cores.RESET}")
    print(f"  Reusados do cache:   {Cores.CIANO}{cached}{Cores.RESET}")
    if erros:
        print(f"  Erros:               {Cores.VERMELHO}{erros}{Cores.RESET}")
    print(f"  Tokens totais:       {tokens:,}")
    print(f"  Relatorio:           {RELATORIO_PATH.name}")
    print(f"  Mapeamento:          {MAPEAMENTO_PATH.name}")
    print()


if __name__ == "__main__":
    main()
