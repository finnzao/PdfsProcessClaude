#!/usr/bin/env python3
import sys, json
from pathlib import Path

ROOT = Path(__file__).parent

def main():
    if len(sys.argv) < 2:
        print("USO: python run.py <extrair|analise|cautelares|litispendencia|status> [args...]")
        return
    cmd = sys.argv[1].lower()
    sys.path.insert(0, str(ROOT))

    if cmd in ("extrair", "extract"):
        from common.extrair_processos import main as m
        m()
    elif cmd in ("status", "info"):
        from common.utils import DIR_TEXTOS, DIR_PDFS
        pdfs = len(list(DIR_PDFS.glob("*.pdf"))) if DIR_PDFS.exists() else 0
        txts = len(list(DIR_TEXTOS.iterdir())) if DIR_TEXTOS.exists() else 0
        print(f"\n  PDFs: {pdfs} | Textos: {txts}")
        for s in ["analisar_processo", "cautelares_get_info", "litispendencia"]:
            p = ROOT / "services" / s / "checkpoint.json"
            if p.exists():
                ck = json.loads(p.read_text())
                print(f"  {s}: {len(ck.get('processos_analisados',{}))} procs | cmd #{ck.get('ultimo_comando',0):03d}")
            else:
                print(f"  {s}: nao iniciado")
        print()
    elif cmd in ("analise", "analisar_processo", "cautelares", "cautelares_get_info", "litispendencia"):
        if len(sys.argv) < 3:
            print(f"  USO: python run.py {cmd} <fila|status|analisar|pausa|marcar|consolidar|reset>")
            return
        mapa = {
            "analise": "services.analisar_processo.main",
            "analisar_processo": "services.analisar_processo.main",
            "cautelares": "services.cautelares_get_info.main",
            "cautelares_get_info": "services.cautelares_get_info.main",
            "litispendencia": "services.litispendencia.main",
        }
        import importlib
        importlib.import_module(mapa[cmd]).executar(sys.argv[2].lower(), sys.argv[3:])
    else:
        print(f"  Desconhecido: {cmd}")

if __name__ == "__main__":
    main()