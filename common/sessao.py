#!/usr/bin/env python3
"""sessao.py — Controle de sessões de trabalho no Claude Code."""

import json
from pathlib import Path
from datetime import datetime


class SessaoManager:
    def __init__(self, ck_path: Path):
        self.path = ck_path

    def _load(self):
        if self.path.exists(): return json.loads(self.path.read_text(encoding='utf-8'))
        return {"criado_em": datetime.now().isoformat(), "ultima_atualizacao": "",
                "processos_analisados": {}, "comandos_concluidos": [], "ultimo_comando": 0, "sessoes": []}

    def _save(self, ck):
        ck["ultima_atualizacao"] = datetime.now().isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding='utf-8')

    def inicio(self):
        """Abre uma sessão."""
        ck = self._load()
        ult = ck.get("ultimo_comando", 0)
        ck.setdefault("sessoes", []).append({"inicio": datetime.now().isoformat(), "fim": None, "cmd_inicio": ult})
        self._save(ck)
        print(f"\n  🟢 SESSÃO #{len(ck['sessoes'])} — Retomar do comando #{ult+1:03d}\n")

    def fim(self, fila_path=None):
        """Fecha a sessão atual."""
        ck = self._load()
        ss = ck.get("sessoes", [])
        if not ss or ss[-1].get("fim"):
            print("  ⚠️  Nenhuma sessão aberta."); return
        agora = datetime.now()
        ss[-1]["fim"] = agora.isoformat()
        ss[-1]["cmd_fim"] = ck.get("ultimo_comando", 0)
        self._save(ck)
        dt = agora - datetime.fromisoformat(ss[-1]["inicio"])
        m = dt.seconds // 60
        total_cmd = 0
        if fila_path and fila_path.exists():
            total_cmd = json.loads(fila_path.read_text()).get("total_comandos", 0)
        rest = total_cmd - ck.get("ultimo_comando", 0)
        print(f"\n  🔴 SESSÃO ENCERRADA ({m}min) | Restam {rest} comandos\n")
