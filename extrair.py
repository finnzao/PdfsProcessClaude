#!/usr/bin/env python3
"""
extrair.py — CLI standalone para extracao de PDFs juridicos -> markdown.

Le PDFs de pdfs/ e gera markdowns em textos_extraidos/, com cache invalidado
por hash do conteudo + hash dos modulos de utils. Workers paralelos sao
calibrados em funcao do tamanho dos PDFs pendentes e do CPU disponivel.

Uso:
    python extrair.py                          # processa pdfs/ -> textos_extraidos/
    python extrair.py --src minha_pasta        # outra pasta de entrada
    python extrair.py --dst saida              # outra pasta de saida
    python extrair.py --workers 4              # forca N workers
    python extrair.py --force                  # ignora cache
    python extrair.py --no-ocr                 # desabilita OCR
    python extrair.py --force-ocr              # OCR em todas as paginas
    python extrair.py --threshold 80           # threshold de OCR
    python extrair.py --dry-run                # mostra fila sem processar
    python extrair.py --status                 # status do cache
    python extrair.py --clean-cache            # limpa cache
    python extrair.py --only PADRAO            # filtra glob
    python extrair.py --debug                  # salva _debug/*.debug.json
    python extrair.py --verbose                # logs detalhados
"""

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.extrator_pdf import (
    DEFAULT_OCR_THRESHOLD,
    cache_key_arquivo,
    processar_pdf,
    versao_utils,
)
from common.utils_io import (
    ensure_dir,
    extrair_numero_processo,
    formato_tamanho,
    formato_tempo,
    ler_json,
    salvar_json,
)


DIR_PDFS_DEFAULT = ROOT / "pdfs"
DIR_SAIDA_DEFAULT = ROOT / "textos_extraidos"
MAPEAMENTO_PATH = ROOT / "mapeamento_processos.json"
RELATORIO_PATH = ROOT / "relatorio_extracao.json"


# ========================================================
#   UI: barra de progresso (rich preferencial, tqdm fallback, plano por ultimo)
# ========================================================

class _ProgressoSimples:
    """Fallback minimalista quando nem rich nem tqdm estao instalados."""

    def __init__(self, total: int):
        self.total = total
        self.feitos = 0
        self.t0 = time.time()

    def avancar(self, label: str = "", extra: str = ""):
        self.feitos += 1
        dt = time.time() - self.t0
        eta = (dt / self.feitos) * (self.total - self.feitos) if self.feitos else 0
        bar_w = 30
        cheio = int((self.feitos / self.total) * bar_w) if self.total else 0
        bar = "#" * cheio + "-" * (bar_w - cheio)
        print(f"  [{bar}] {self.feitos}/{self.total}  {label[:40]:<40}  {extra}  ETA {int(eta)}s")

    def close(self):
        pass


def _criar_progresso(total: int, label_geral: str):
    """Tenta rich -> tqdm -> simples. Retorna (objeto, modo)."""
    try:
        from rich.progress import (
            BarColumn, Progress, TaskProgressColumn,
            TextColumn, TimeRemainingColumn,
        )
        prog = Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=30),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            TextColumn("{task.fields[extra]}"),
        )
        prog.start()
        task_id = prog.add_task(label_geral, total=total, extra="")
        return ("rich", prog, task_id)
    except ImportError:
        pass

    try:
        from tqdm import tqdm
        bar = tqdm(total=total, desc=label_geral, ncols=100)
        return ("tqdm", bar, None)
    except ImportError:
        pass

    return ("simples", _ProgressoSimples(total), None)


def _avancar_progresso(progresso, label: str = "", extra: str = ""):
    modo, obj, task_id = progresso
    if modo == "rich":
        obj.update(task_id, advance=1, extra=extra[:50])
    elif modo == "tqdm":
        obj.set_postfix_str(extra[:50])
        obj.update(1)
    else:
        obj.avancar(label, extra)


def _fechar_progresso(progresso):
    modo, obj, _ = progresso
    if modo == "rich":
        obj.stop()
    elif modo == "tqdm":
        obj.close()
    else:
        obj.close()


# ========================================================
#   Banner
# ========================================================

def banner():
    print()
    print("=" * 64)
    print("  EXTRATOR PDF -> MARKDOWN  |  PJe / TJBA")
    print("=" * 64)


# ========================================================
#   Dependencias
# ========================================================

def verificar_dependencias():
    """Checa pymupdf4llm (obrigatorio) e pytesseract (opcional)."""
    faltando = []
    try:
        import pymupdf4llm  # noqa: F401
        print("  [OK] pymupdf4llm")
    except ImportError:
        faltando.append("pymupdf4llm")

    try:
        import pymupdf  # noqa: F401
        print("  [OK] pymupdf")
    except ImportError:
        faltando.append("pymupdf")

    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        print("  [OK] pytesseract + Pillow (OCR ativo)")
        ocr_disponivel = True
    except ImportError:
        print("  [--] pytesseract ausente — OCR desativado")
        ocr_disponivel = False

    try:
        import cv2  # noqa: F401
        print("  [OK] opencv-python (Otsu/deskew acelerados)")
    except ImportError:
        print("  [--] opencv-python ausente — fallback numpy")

    if faltando:
        print(f"\n  Instale: pip install {' '.join(faltando)}")
        sys.exit(1)

    return ocr_disponivel


# ========================================================
#   Cache
# ========================================================

def carregar_cache():
    return ler_json(MAPEAMENTO_PATH, default={})


def salvar_cache(mapa):
    salvar_json(MAPEAMENTO_PATH, mapa)


def status_cache(dir_pdfs, dir_saida):
    cache = carregar_cache()
    pdfs = list(dir_pdfs.glob("*.pdf")) if dir_pdfs.exists() else []
    mds = list(dir_saida.glob("*.md")) if dir_saida.exists() else []

    print(f"\n  Status do cache")
    print(f"  {'-' * 50}")
    print(f"  PDFs em {dir_pdfs.name}/:           {len(pdfs)}")
    print(f"  Markdowns em {dir_saida.name}/:      {len(mds)}")
    print(f"  Entradas em mapeamento_processos:   {len(cache)}")
    print(f"  Versao atual de utils:              {versao_utils()}")

    if not cache:
        print("\n  Cache vazio.")
        return

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

    print(f"\n  Cache valido:           {validos}")
    print(f"  Cache invalidado:       {invalidos} (versao utils mudou)")
    print(f"  Cache orfao:            {orfaos} (md deletado)")
    print()


def limpar_cache():
    if MAPEAMENTO_PATH.exists():
        MAPEAMENTO_PATH.unlink()
        print(f"  OK  Cache limpo: {MAPEAMENTO_PATH.name}")
    else:
        print("  Cache ja vazio.")
    if RELATORIO_PATH.exists():
        RELATORIO_PATH.unlink()
        print("  OK  Relatorio anterior removido.")


# ========================================================
#   Pipeline
# ========================================================

def listar_pdfs(dir_pdfs, padrao_glob=None):
    if not dir_pdfs.exists():
        return []
    if padrao_glob:
        return sorted(dir_pdfs.glob(padrao_glob))
    return sorted(dir_pdfs.glob("*.pdf"))


def filtrar_pendentes(pdfs, dir_saida, cache, force=False):
    pendentes = []
    pulados = []
    for pdf in pdfs:
        ck = cache_key_arquivo(pdf)
        if force:
            pendentes.append(pdf)
            continue
        numero = extrair_numero_processo(pdf.name)
        entrada = cache.get(numero, {})
        if entrada.get("cache_key") == ck:
            md_path = dir_saida / entrada.get("md", "")
            if md_path.exists():
                pulados.append((pdf, entrada))
                continue
        pendentes.append(pdf)
    return pendentes, pulados


def workers_adaptativos(pendentes: list[Path], hint: int) -> int:
    """
    Calcula numero de workers em funcao do CPU, RAM e tamanho dos PDFs.

    Regras:
      - Se o usuario passou --workers explicito, respeita (cap 16).
      - PDFs > 50MB consomem muita RAM no OCR -> menos workers.
      - Cap em min(CPU//2, 4, n_pendentes) por padrao.
    """
    if hint > 0:
        return max(1, min(hint, 16, len(pendentes)))

    if not pendentes:
        return 1

    n_cpu = os.cpu_count() or 4
    n_pdfs = len(pendentes)

    tamanho_medio = sum(p.stat().st_size for p in pendentes) / n_pdfs
    if tamanho_medio > 50 * 1024 * 1024:
        teto = 2
    elif tamanho_medio > 20 * 1024 * 1024:
        teto = 3
    else:
        teto = 4

    return max(1, min(n_cpu // 2, teto, n_pdfs))


def _executar_paralelo(pdfs, dir_saida, opts, n_workers, total_label):
    resultados = []
    total = len(pdfs)

    print(f"\n  Processando {total} PDF(s) com {n_workers} worker(s)")
    print(f"  {'-' * 50}")

    progresso = _criar_progresso(total, total_label)
    t_inicio = time.time()

    with ProcessPoolExecutor(max_workers=n_workers) as exe:
        futures = {
            exe.submit(processar_pdf, str(p), str(dir_saida), opts): p
            for p in pdfs
        }
        for fut in as_completed(futures):
            pdf = futures[fut]
            try:
                r = fut.result()
                if r["status"] == "OK":
                    ocr = f" OCR={r.get('paginas_ocr', 0)}" if r.get("paginas_ocr") else ""
                    extra = f"{r['tokens_aprox']:>6,} tok | {r['pecas']:>3} pecas{ocr}"
                else:
                    extra = f"ERRO: {r.get('erro', '?')[:30]}"
            except Exception as e:
                r = {"arquivo": pdf.name, "status": "ERRO", "erro": str(e), "numero": pdf.stem}
                extra = f"ERRO: {str(e)[:30]}"
            resultados.append(r)
            _avancar_progresso(progresso, pdf.name, extra)

    _fechar_progresso(progresso)
    dt = time.time() - t_inicio
    return resultados, dt


def _executar_serial(pdfs, dir_saida, opts):
    resultados = []
    total = len(pdfs)

    print(f"\n  Processando {total} PDF(s) (modo serial)")
    print(f"  {'-' * 50}")

    progresso = _criar_progresso(total, "Extraindo")
    t_inicio = time.time()
    for pdf in pdfs:
        try:
            r = processar_pdf(str(pdf), str(dir_saida), opts)
            if r["status"] == "OK":
                ocr = f" OCR={r.get('paginas_ocr', 0)}" if r.get("paginas_ocr") else ""
                extra = f"{r['tokens_aprox']:,} tok{ocr}"
            else:
                extra = f"ERRO: {r.get('erro', '?')[:30]}"
        except Exception as e:
            r = {"arquivo": pdf.name, "status": "ERRO", "erro": str(e), "numero": pdf.stem}
            extra = f"ERRO: {str(e)[:30]}"
        resultados.append(r)
        _avancar_progresso(progresso, pdf.name, extra)

    _fechar_progresso(progresso)
    dt = time.time() - t_inicio
    return resultados, dt


def main():
    parser = argparse.ArgumentParser(
        prog="extrair",
        description="Extrai PDFs juridicos para markdown otimizado para LLM",
    )
    parser.add_argument("--src", type=str, default=str(DIR_PDFS_DEFAULT),
                        help=f"pasta de PDFs (default: {DIR_PDFS_DEFAULT.name}/)")
    parser.add_argument("--dst", type=str, default=str(DIR_SAIDA_DEFAULT),
                        help=f"pasta de saida (default: {DIR_SAIDA_DEFAULT.name}/)")
    parser.add_argument("--workers", type=int, default=0,
                        help="processos paralelos (0=auto baseado em CPU/RAM)")
    parser.add_argument("--force", action="store_true", help="ignora cache")
    parser.add_argument("--no-ocr", action="store_true", help="desabilita OCR")
    parser.add_argument("--force-ocr", action="store_true", help="OCR em todas as paginas")
    parser.add_argument("--threshold", type=int, default=DEFAULT_OCR_THRESHOLD,
                        help=f"threshold de OCR (default: {DEFAULT_OCR_THRESHOLD})")
    parser.add_argument("--dry-run", action="store_true", help="mostra fila sem processar")
    parser.add_argument("--status", action="store_true", help="status do cache")
    parser.add_argument("--clean-cache", action="store_true", help="limpa cache")
    parser.add_argument("--only", type=str, default=None, help="glob ex: '8001*.pdf'")
    parser.add_argument("--debug", action="store_true", help="salva _debug/*.debug.json")
    parser.add_argument("--verbose", "-v", action="store_true", help="logs detalhados")
    args = parser.parse_args()

    dir_pdfs = Path(args.src).resolve()
    dir_saida = Path(args.dst).resolve()
    ensure_dir(dir_saida)

    banner()

    if args.clean_cache:
        limpar_cache()
        return
    if args.status:
        status_cache(dir_pdfs, dir_saida)
        return

    print("  Configuracao")
    print(f"  {'-' * 50}")
    print(f"  Entrada:    {dir_pdfs}")
    print(f"  Saida:      {dir_saida}")
    print(f"  Workers:    {args.workers if args.workers > 0 else 'auto'}")
    print(f"  OCR:        {'desabilitado' if args.no_ocr else ('forcado' if args.force_ocr else f'auto (threshold={args.threshold})')}")
    print(f"  Cache:      {'ignorado (--force)' if args.force else 'ativo'}")
    print(f"  Debug:      {'salva _debug/' if args.debug else 'off'}")
    if args.only:
        print(f"  Filtro:     {args.only}")
    print()

    if not args.dry_run:
        print("  Verificando dependencias")
        print(f"  {'-' * 50}")
        ocr_disponivel = verificar_dependencias()
    else:
        ocr_disponivel = False

    pdfs = listar_pdfs(dir_pdfs, padrao_glob=args.only)
    if not pdfs:
        print(f"\n  Nenhum PDF encontrado em {dir_pdfs}/")
        if not dir_pdfs.exists():
            print(f"  Crie: mkdir -p {dir_pdfs.relative_to(ROOT)}")
        return

    cache = carregar_cache()
    pendentes, pulados = filtrar_pendentes(pdfs, dir_saida, cache, force=args.force)

    print("\n  Inventario")
    print(f"  {'-' * 50}")
    print(f"  Total de PDFs:     {len(pdfs)}")
    print(f"  Em cache valido:   {len(pulados)}")
    print(f"  A processar:       {len(pendentes)}")
    tamanho_total = sum(p.stat().st_size for p in pendentes)
    print(f"  Tamanho total:     {formato_tamanho(tamanho_total)}")

    if args.dry_run:
        print("\n  DRY-RUN — nada sera processado")
        for p in pendentes[:20]:
            print(f"    {p.name}  ({formato_tamanho(p.stat().st_size)})")
        if len(pendentes) > 20:
            print(f"    ... +{len(pendentes) - 20} arquivos")
        return

    if not pendentes:
        print("\n  Tudo em cache. Nada a fazer.")
        print("  Use --force para reprocessar tudo.\n")
        return

    n_workers = workers_adaptativos(pendentes, args.workers)

    opts = {
        "use_ocr": not args.no_ocr and ocr_disponivel,
        "force_ocr": args.force_ocr and ocr_disponivel,
        "ocr_threshold": args.threshold,
        "verbose": args.verbose,
        "debug": args.debug,
        "skip_se_md_igual": not args.force,
    }

    if n_workers <= 1 or len(pendentes) <= 1:
        resultados, dt = _executar_serial(pendentes, dir_saida, opts)
    else:
        resultados, dt = _executar_paralelo(pendentes, dir_saida, opts, n_workers, "Extraindo")

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

    for pdf, entrada in pulados:
        resultados.append({
            "arquivo": pdf.name,
            "numero": extrair_numero_processo(pdf.name),
            "arquivo_saida": entrada.get("md", ""),
            "tokens_aprox": entrada.get("tokens", 0),
            "cache_key": entrada.get("cache_key", ""),
            "status": "CACHE",
        })

    ok = sum(1 for r in resultados if r["status"] == "OK")
    cached = sum(1 for r in resultados if r["status"] == "CACHE")
    erros = sum(1 for r in resultados if r["status"] == "ERRO")
    tokens = sum(r.get("tokens_aprox", 0) for r in resultados)
    paginas_ocr = sum(r.get("paginas_ocr", 0) for r in resultados if r.get("status") == "OK")
    nao_reescritos = sum(1 for r in resultados if r.get("status") == "OK" and not r.get("md_reescrito", True))

    salvar_json(RELATORIO_PATH, {
        "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tempo_s": round(dt, 2),
        "total": len(resultados),
        "ok": ok,
        "cache": cached,
        "erros": erros,
        "tokens_total": tokens,
        "paginas_ocr_total": paginas_ocr,
        "md_nao_reescritos": nao_reescritos,
        "config": opts,
        "n_workers": n_workers,
        "processos": resultados,
    })

    print("\n  Concluido")
    print(f"  {'-' * 50}")
    print(f"  Tempo:               {formato_tempo(dt)}")
    print(f"  Processados agora:   {ok}")
    print(f"  Reusados do cache:   {cached}")
    if erros:
        print(f"  Erros:               {erros}")
    print(f"  Paginas com OCR:     {paginas_ocr}")
    print(f"  MDs nao reescritos:  {nao_reescritos} (conteudo identico)")
    print(f"  Tokens totais:       {tokens:,}")
    print(f"  Relatorio:           {RELATORIO_PATH.name}")
    print(f"  Mapeamento:          {MAPEAMENTO_PATH.name}")
    print()


if __name__ == "__main__":
    main()
