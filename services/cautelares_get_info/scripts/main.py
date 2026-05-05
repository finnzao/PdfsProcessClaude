#!/usr/bin/env python3
"""
main.py — CLI do serviço de cadastro de custodiados.

Roda a partir da raiz do projeto:
    python -m services.cautelares_get_info.scripts.main <comando>

Comandos:
    reconciliar   cruza lista do papel com PJe (xlsx + csv → relatório)
    pre-extrair   markdown → JSON com qualificação + cautelar (sem LLM)
    consolidar    JSONs → planilha xlsx final (CadastroInicialDTO)
    pipeline      roda os três em sequência

Exemplos:
    python -m services.cautelares_get_info.scripts.main reconciliar
    python -m services.cautelares_get_info.scripts.main pre-extrair
    python -m services.cautelares_get_info.scripts.main consolidar
    python -m services.cautelares_get_info.scripts.main pipeline

Flags:
    --overwrite   força reprocessamento de JSONs existentes
"""

import argparse
import sys
from pathlib import Path

# Garante que a raiz do projeto está no sys.path quando o script é
# executado diretamente. Sobe 3 níveis: scripts/ → cautelares_get_info/ →
# services/ → raiz.
RAIZ = Path(__file__).resolve().parents[3]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from common.reconciliador import Reconciliador
from services.cautelares_get_info.scripts.pre_extracao import processar_lote
from services.cautelares_get_info.scripts.consolidar import consolidar


# Caminhos default (relativos à raiz do projeto)
DEFAULT_LISTA_PAPEL = RAIZ / "files" / "lista_cadastro_scc.xlsx"
DEFAULT_CSV_PJE     = RAIZ / "files" / "scc_info.csv"
DEFAULT_TEXTOS_MD   = RAIZ / "textos_extraidos"
DEFAULT_PRE_EXTRAIDO = RAIZ / "pre_extraido"
DEFAULT_RESULT      = RAIZ / "result"


def cmd_reconciliar(args: argparse.Namespace) -> None:
    rec = Reconciliador()
    rec.carregar_lista_papel(args.lista or DEFAULT_LISTA_PAPEL)
    rec.carregar_pje(args.csv or DEFAULT_CSV_PJE)
    rec.reconciliar()
    saida = Path(args.saida) if args.saida else DEFAULT_RESULT / "reconciliacao_papel_pje.xlsx"
    rec.exportar_relatorio(saida)
    rec.exportar_json(saida.with_suffix(".json"))


def cmd_pre_extrair(args: argparse.Namespace) -> None:
    md_dir = Path(args.md_dir) if args.md_dir else DEFAULT_TEXTOS_MD
    out_dir = Path(args.json_dir) if args.json_dir else DEFAULT_PRE_EXTRAIDO
    if not md_dir.exists():
        print(f"  Diretório não existe: {md_dir}", file=sys.stderr)
        sys.exit(1)
    processar_lote(md_dir, out_dir, overwrite=args.overwrite)


def cmd_consolidar(args: argparse.Namespace) -> None:
    json_dir = Path(args.json_dir) if args.json_dir else DEFAULT_PRE_EXTRAIDO
    lista = Path(args.lista) if args.lista else DEFAULT_LISTA_PAPEL
    saida = Path(args.saida) if args.saida else DEFAULT_RESULT / "cadastro_inicial.xlsx"
    consolidar(json_dir, lista if lista.exists() else None, saida)


def cmd_pipeline(args: argparse.Namespace) -> None:
    print("\n" + "=" * 60)
    print("  PIPELINE DE CUSTODIADOS — Vara Criminal de Rio Real")
    print("=" * 60)

    print("\n[1/3] Reconciliando papel ↔ PJe...")
    cmd_reconciliar(args)

    print("\n[2/3] Pré-extração regex dos markdowns...")
    cmd_pre_extrair(args)

    print("\n[3/3] Consolidando planilha final...")
    cmd_consolidar(args)

    print("\n" + "=" * 60)
    print("  PIPELINE CONCLUÍDO")
    print("=" * 60)
    print("\nArquivos gerados:")
    print(f"  • {DEFAULT_RESULT / 'reconciliacao_papel_pje.xlsx'}")
    print(f"  • {DEFAULT_PRE_EXTRAIDO}/*.json")
    print(f"  • {DEFAULT_RESULT / 'cadastro_inicial.xlsx'}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main",
        description="Pipeline de custodiados — Vara Criminal de Rio Real (SCC)",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_rec = sub.add_parser("reconciliar", help="Cruza lista do papel com PJe")
    p_rec.add_argument("--lista", help="xlsx da lista do papel")
    p_rec.add_argument("--csv", help="csv exportado do PJe")
    p_rec.add_argument("--saida", help="xlsx de saída")
    p_rec.set_defaults(func=cmd_reconciliar)

    p_pre = sub.add_parser("pre-extrair", help="Pré-extrai dados de markdowns")
    p_pre.add_argument("md_dir", nargs="?", help="diretório com .md")
    p_pre.add_argument("json_dir", nargs="?", help="diretório de saída (.json)")
    p_pre.add_argument("--overwrite", action="store_true", help="reprocessa JSONs existentes")
    p_pre.set_defaults(func=cmd_pre_extrair)

    p_con = sub.add_parser("consolidar", help="Gera planilha final de cadastro")
    p_con.add_argument("--json-dir", dest="json_dir", help="diretório dos JSONs")
    p_con.add_argument("--lista", help="xlsx da lista do papel")
    p_con.add_argument("--saida", help="xlsx de saída")
    p_con.set_defaults(func=cmd_consolidar)

    p_pip = sub.add_parser("pipeline", help="Roda os três comandos em sequência")
    p_pip.add_argument("--lista")
    p_pip.add_argument("--csv")
    p_pip.add_argument("--md-dir", dest="md_dir")
    p_pip.add_argument("--json-dir", dest="json_dir")
    p_pip.add_argument("--saida")
    p_pip.add_argument("--overwrite", action="store_true")
    p_pip.set_defaults(func=cmd_pipeline)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
