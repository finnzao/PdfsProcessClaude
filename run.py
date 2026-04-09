#!/usr/bin/env python3
"""
run.py — CLI unificado para todas as missões do projeto.

USO:
    python run.py extrair                  # Extrai PDFs (compartilhado)
    python run.py analise <comando>        # Missão 1: Análise jurídica
    python run.py cautelares <comando>     # Missão 2: Custodiados
    python run.py status                   # Status geral de tudo

COMANDOS POR SERVICE:
    fila        Gera fila de comandos para Claude Code
    status      Mostra progresso
    analisar    Registra início de sessão
    pausa       Registra fim de sessão
    marcar N P  Marca comando como concluído
    consolidar  Gera relatório/planilha final
    reset       Recomeça do zero
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent


def cmd_extrair():
    sys.path.insert(0, str(PROJECT_ROOT))
    from common.extrair_processos import main
    main()


def cmd_service(service_alias, comando, args):
    sys.path.insert(0, str(PROJECT_ROOT))

    service_map = {
        "analise": "services.analisar_processo.main",
        "analisar_processo": "services.analisar_processo.main",
        "cautelares": "services.cautelares_get_info.main",
        "cautelares_get_info": "services.cautelares_get_info.main",
    }

    module_name = service_map.get(service_alias)
    if not module_name:
        print(f"  Service desconhecido: {service_alias}")
        print(f"  Disponíveis: {', '.join(service_map.keys())}")
        return

    import importlib
    mod = importlib.import_module(module_name)
    mod.executar(comando, args)


def cmd_status():
    sys.path.insert(0, str(PROJECT_ROOT))
    from common.utils import DIR_TEXTOS, DIR_PDFS

    pdfs = len(list(DIR_PDFS.glob("*.pdf"))) if DIR_PDFS.exists() else 0
    txts = len(list(DIR_TEXTOS.iterdir())) if DIR_TEXTOS.exists() else 0

    print()
    print("=" * 60)
    print("  STATUS GERAL DO PROJETO")
    print("=" * 60)
    print(f"  PDFs:              {pdfs}")
    print(f"  Textos extraídos:  {txts}")
    print()

    for service_name, alias in [("analisar_processo", "analise"),
                                 ("cautelares_get_info", "cautelares")]:
        service_dir = PROJECT_ROOT / "services" / service_name
        ck_path = service_dir / "checkpoint.json"
        if ck_path.exists():
            import json
            with open(ck_path, 'r') as f:
                ck = json.load(f)
            total = len(ck.get("processos_analisados", {}))
            ultimo = ck.get("ultimo_comando", 0)
            print(f"  {service_name}:")
            print(f"    Processos: {total} | Último cmd: #{ultimo:03d}")
        else:
            print(f"  {service_name}: não iniciado")
    print()


def mostrar_ajuda():
    print(__doc__)
    print("EXEMPLOS:")
    print("  python run.py extrair")
    print("  python run.py analise fila")
    print("  python run.py analise analisar")
    print("  python run.py analise marcar 1 0000770-14.2020.8.05.0216")
    print("  python run.py cautelares fila")
    print("  python run.py cautelares consolidar")
    print("  python run.py status")
    print()


def main():
    if len(sys.argv) < 2:
        mostrar_ajuda()
        return

    cmd = sys.argv[1].lower()

    if cmd in ("extrair", "extract"):
        cmd_extrair()
    elif cmd in ("status", "info"):
        cmd_status()
    elif cmd in ("help", "--help", "-h"):
        mostrar_ajuda()
    elif cmd in ("analise", "analisar_processo", "cautelares", "cautelares_get_info"):
        if len(sys.argv) < 3:
            print(f"  USO: python run.py {cmd} <comando>")
            print(f"  Comandos: fila, status, analisar, pausa, marcar, consolidar, reset")
            return
        subcmd = sys.argv[2].lower()
        args = sys.argv[3:]
        cmd_service(cmd, subcmd, args)
    else:
        print(f"  Comando desconhecido: {cmd}")
        mostrar_ajuda()


if __name__ == "__main__":
    main()
