"""scripts/main.py — CLI orquestradora do pipeline cautelares_get_info."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent.parent.parent))


def cmd_pre_extracao(args):
    from services.cautelares_get_info.scripts import pre_extracao as mod
    mod.main()


def cmd_fila(args):
    from services.cautelares_get_info.scripts import fila_extracao as mod
    sys.argv = ["fila_extracao.py", "--batch", str(args.batch)]
    mod.main()


def cmd_consolidar(args):
    from services.cautelares_get_info.scripts import consolidar_extracao as mod
    mod.consolidar()


def main():
    ap = argparse.ArgumentParser(
        description="Pipeline de extracao de custodiados (cautelares_get_info)."
    )
    sub = ap.add_subparsers(dest="acao", required=True)

    p_pre = sub.add_parser("pre-extracao", help="Identifica processos elegiveis nos .md")
    p_pre.set_defaults(func=cmd_pre_extracao)

    p_fila = sub.add_parser("fila", help="Monta fila_extracao.json e comandos_extracao.txt")
    p_fila.add_argument("--batch", type=int, default=5)
    p_fila.set_defaults(func=cmd_fila)

    p_cons = sub.add_parser("consolidar", help="Consolida resultados em planilha xlsx")
    p_cons.set_defaults(func=cmd_consolidar)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
