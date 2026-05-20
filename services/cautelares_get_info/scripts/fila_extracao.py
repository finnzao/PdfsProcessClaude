"""scripts/fila_extracao.py — Gera fila_extracao.json e comandos_extracao.txt."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
SERVICE_DIR = ROOT / "services" / "cautelares_get_info"
PRE_PATH = SERVICE_DIR / "pre_extracao.json"
FILA_PATH = SERVICE_DIR / "fila_extracao.json"
CMDS_PATH = SERVICE_DIR / "comandos_extracao.txt"
PROMPT_BASE_PATH = SERVICE_DIR / "prompts" / "prompt_extracao.md"

DEFAULT_BATCH = 5


def carregar_pre_extracao() -> list[dict]:
    if not PRE_PATH.exists():
        return []
    dados = json.loads(PRE_PATH.read_text(encoding="utf-8"))
    return dados.get("itens", [])


def montar_fila(itens: list[dict], tamanho_batch: int) -> dict:
    comandos = []
    for idx_inicio in range(0, len(itens), tamanho_batch):
        num_cmd = (idx_inicio // tamanho_batch) + 1
        bloco = itens[idx_inicio : idx_inicio + tamanho_batch]
        comandos.append({
            "num": num_cmd,
            "processos": [b["numero_processo"] for b in bloco],
            "arquivos_md": [b["arquivo_md"] for b in bloco],
        })
    return {
        "gerada_em": datetime.now().isoformat(),
        "total_itens": len(itens),
        "tamanho_batch": tamanho_batch,
        "total_comandos": len(comandos),
        "comandos": comandos,
    }


def montar_comandos_txt(fila: dict) -> str:
    """Monta arquivo de comandos um bloco por CMD."""
    if not PROMPT_BASE_PATH.exists():
        prompt_base = "(prompt_extracao.md ausente)"
    else:
        prompt_base = PROMPT_BASE_PATH.read_text(encoding="utf-8")

    linhas = [
        "# Comandos para Claude Code — Extracao de Custodiados",
        "# Cada bloco '# === CMD NNN ===' e um prompt independente.",
        "",
    ]
    for cmd in fila["comandos"]:
        linhas.append(f"# === CMD {cmd['num']:03d} ===")
        linhas.append("")
        linhas.append(prompt_base.rstrip())
        linhas.append("")
        linhas.append("## Processos a extrair neste batch:")
        for n, arq in zip(cmd["processos"], cmd["arquivos_md"]):
            linhas.append(f"  - {n}  (md: pre_extraido/{arq})")
        linhas.append("")
        linhas.append(f"Salve em: services/cautelares_get_info/resultados/extracao/extracao_{cmd['num']:03d}.json")
        linhas.append("")
        linhas.append("---")
        linhas.append("")
    return "\n".join(linhas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH,
                    help=f"Tamanho de cada batch (default {DEFAULT_BATCH})")
    args = ap.parse_args()

    itens = carregar_pre_extracao()
    if not itens:
        print(f"  Nenhum item em {PRE_PATH}. Rode pre_extracao.py primeiro.")
        return

    fila = montar_fila(itens, args.batch)
    FILA_PATH.write_text(
        json.dumps(fila, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  fila_extracao.json: {fila['total_comandos']} comandos, {fila['total_itens']} processos")

    txt = montar_comandos_txt(fila)
    CMDS_PATH.write_text(txt, encoding="utf-8")
    print(f"  comandos_extracao.txt: {CMDS_PATH}")


if __name__ == "__main__":
    main()
