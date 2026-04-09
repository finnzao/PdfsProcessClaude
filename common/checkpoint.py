#!/usr/bin/env python3
"""
checkpoint.py — Gerenciador de checkpoint genérico para qualquer service.

USO:
    from common.checkpoint import CheckpointManager
    cm = CheckpointManager(Path("services/meu_service/checkpoint.json"))
    cm.marcar_concluido(cmd_num=1, processos=["0000770-14.2020.8.05.0216"])
"""

import json
import sys
from pathlib import Path
from datetime import datetime


class CheckpointManager:
    def __init__(self, checkpoint_path: Path):
        self.path = checkpoint_path

    def carregar(self):
        if self.path.exists():
            with open(self.path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "criado_em": datetime.now().isoformat(),
            "ultima_atualizacao": datetime.now().isoformat(),
            "processos_analisados": {},
            "comandos_concluidos": [],
            "ultimo_comando": 0,
            "sessoes": []
        }

    def salvar(self, ck):
        ck["ultima_atualizacao"] = datetime.now().isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(ck, f, ensure_ascii=False, indent=2)

    def marcar_concluido(self, cmd_num, processos, resultado_path=""):
        ck = self.carregar()
        if cmd_num not in ck["comandos_concluidos"]:
            ck["comandos_concluidos"].append(cmd_num)
            ck["comandos_concluidos"].sort()

        if cmd_num > ck.get("ultimo_comando", 0):
            ck["ultimo_comando"] = cmd_num

        agora = datetime.now().isoformat()
        for proc in processos:
            ck["processos_analisados"][proc] = {
                "comando": cmd_num,
                "data": agora,
                "arquivo_resultado": resultado_path
            }

        self.salvar(ck)

        total = len(ck["processos_analisados"])
        cmds = len(ck["comandos_concluidos"])
        print(f"  ✅ Comando #{cmd_num:03d} concluído")
        print(f"     Processos marcados: {len(processos)}")
        print(f"     Total analisados: {total} | Comandos feitos: {cmds}")

    def processos_ja_analisados(self):
        ck = self.carregar()
        return set(ck.get("processos_analisados", {}).keys())

    def ultimo_comando(self):
        ck = self.carregar()
        return ck.get("ultimo_comando", 0)

    def reset(self):
        if self.path.exists():
            self.path.unlink()
        print("  Checkpoint resetado.")
