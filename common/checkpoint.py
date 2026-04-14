#!/usr/bin/env python3
"""checkpoint.py — Rastreia quais comandos/processos já foram feitos."""

import json
from pathlib import Path
from datetime import datetime


class CheckpointManager:
    def __init__(self, path: Path):
        self.path = path

    def carregar(self):
        if self.path.exists():
            return json.loads(self.path.read_text(encoding='utf-8'))
        return {"criado_em": datetime.now().isoformat(), "ultima_atualizacao": "",
                "processos_analisados": {}, "comandos_concluidos": [], "ultimo_comando": 0, "sessoes": []}

    def salvar(self, ck):
        ck["ultima_atualizacao"] = datetime.now().isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding='utf-8')

    def marcar_concluido(self, cmd_num, processos, resultado_path=""):
        """Registra comando como feito e os processos associados."""
        ck = self.carregar()
        if cmd_num not in ck["comandos_concluidos"]:
            ck["comandos_concluidos"].append(cmd_num)
            ck["comandos_concluidos"].sort()
        if cmd_num > ck.get("ultimo_comando", 0):
            ck["ultimo_comando"] = cmd_num
        agora = datetime.now().isoformat()
        for p in processos:
            ck["processos_analisados"][p] = {"comando": cmd_num, "data": agora, "arquivo": resultado_path}
        self.salvar(ck)
        print(f"  OK Comando #{cmd_num:03d} | {len(processos)} processos | Total: {len(ck['processos_analisados'])}")

    def processos_ja_analisados(self):
        return set(self.carregar().get("processos_analisados", {}).keys())

    def ultimo_comando(self):
        return self.carregar().get("ultimo_comando", 0)

    def reset(self):
        if self.path.exists(): self.path.unlink()
        print("  Checkpoint resetado.")
