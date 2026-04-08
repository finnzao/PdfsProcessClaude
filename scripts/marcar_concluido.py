#!/usr/bin/env python3
"""
marcar_concluido.py — Marca um comando como concluído no checkpoint.

USO:
    python3 scripts/marcar_concluido.py <NUM_COMANDO> <PROCESSO1> [PROCESSO2] ...

EXEMPLO:
    python3 scripts/marcar_concluido.py 1 0000770-14.2020.8.05.0216 8000994-73.2021.8.05.0216

Atualiza checkpoint.json com:
- Comando marcado como concluído
- Processos marcados como analisados
- Horário registrado
"""

import json
import sys
from pathlib import Path
from datetime import datetime

CHECKPOINT_FILE = Path("checkpoint.json")


def main():
    if len(sys.argv) < 2:
        print("USO: python3 scripts/marcar_concluido.py <NUM_COMANDO> [PROCESSOS...]")
        print("EXEMPLO: python3 scripts/marcar_concluido.py 1 0000770-14.2020.8.05.0216")
        sys.exit(1)

    cmd_num = int(sys.argv[1])
    processos = sys.argv[2:] if len(sys.argv) > 2 else []

    # Carregar checkpoint
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            ck = json.load(f)
    else:
        ck = {
            "criado_em": datetime.now().isoformat(),
            "ultima_atualizacao": datetime.now().isoformat(),
            "processos_analisados": {},
            "comandos_concluidos": [],
            "ultimo_comando": 0,
            "sessoes": []
        }

    # Marcar comando
    if cmd_num not in ck["comandos_concluidos"]:
        ck["comandos_concluidos"].append(cmd_num)
        ck["comandos_concluidos"].sort()

    # Atualizar último comando
    if cmd_num > ck.get("ultimo_comando", 0):
        ck["ultimo_comando"] = cmd_num

    # Marcar processos
    agora = datetime.now().isoformat()
    for proc in processos:
        ck["processos_analisados"][proc] = {
            "comando": cmd_num,
            "data": agora,
            "arquivo_resultado": f"resultados/analise_{cmd_num:03d}.csv"
        }

    ck["ultima_atualizacao"] = agora

    # Salvar
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(ck, f, ensure_ascii=False, indent=2)

    total = len(ck["processos_analisados"])
    cmds = len(ck["comandos_concluidos"])

    print(f"  ✅ Comando #{cmd_num:03d} concluído")
    print(f"     Processos marcados: {len(processos)}")
    print(f"     Total analisados: {total}")
    print(f"     Comandos feitos: {cmds}")

    # Verificar fila para mostrar progresso
    fila_path = Path("fila_analise.json")
    if fila_path.exists():
        with open(fila_path, 'r') as f:
            fila = json.load(f)
        total_cmd = fila.get("total_comandos", 0)
        total_proc = fila.get("total_processos", 0)
        pct = (total / total_proc * 100) if total_proc else 0
        restantes = total_cmd - cmd_num
        print(f"\n     Progresso: {pct:.1f}% ({total}/{total_proc})")
        if restantes > 0:
            print(f"     Restam: {restantes} comandos (~{restantes*5}-{restantes*8} min)")
            print(f"     ▶ Próximo: COMANDO {cmd_num + 1:03d}")
        else:
            print(f"     🎉 ANÁLISE COMPLETA! Rode: python3 scripts/consolidar.py")


if __name__ == "__main__":
    main()
