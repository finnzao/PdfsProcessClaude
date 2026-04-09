#!/usr/bin/env python3
"""
sessao.py — Controle de sessão do Claude Code (genérico para qualquer service).

USO:
    from common.sessao import SessaoManager
    sm = SessaoManager(checkpoint_path)
    sm.inicio()
    sm.fim()
    sm.info()
"""

import json
from pathlib import Path
from datetime import datetime


class SessaoManager:
    def __init__(self, checkpoint_path: Path):
        self.checkpoint_path = checkpoint_path

    def _carregar(self):
        if self.checkpoint_path.exists():
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "criado_em": datetime.now().isoformat(),
            "ultima_atualizacao": datetime.now().isoformat(),
            "processos_analisados": {},
            "comandos_concluidos": [],
            "ultimo_comando": 0,
            "sessoes": []
        }

    def _salvar(self, ck):
        ck["ultima_atualizacao"] = datetime.now().isoformat()
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(ck, f, ensure_ascii=False, indent=2)

    def inicio(self):
        ck = self._carregar()
        ultimo_cmd = ck.get("ultimo_comando", 0)
        sessao = {
            "inicio": datetime.now().isoformat(),
            "fim": None,
            "cmd_inicio": ultimo_cmd,
            "cmd_fim": None,
            "comandos_feitos": 0
        }
        ck.setdefault("sessoes", []).append(sessao)
        self._salvar(ck)

        num = len(ck["sessoes"])
        print(f"\n  🟢 SESSÃO #{num} INICIADA")
        print(f"     Horário: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        print(f"     Retomar de: Comando #{ultimo_cmd + 1:03d}")
        print()

    def fim(self, fila_path=None):
        ck = self._carregar()
        sessoes = ck.get("sessoes", [])

        if not sessoes or sessoes[-1].get("fim"):
            print("  ⚠️  Nenhuma sessão aberta.")
            return

        agora = datetime.now()
        ultimo_cmd = ck.get("ultimo_comando", 0)
        sessao = sessoes[-1]
        sessao["fim"] = agora.isoformat()
        sessao["cmd_fim"] = ultimo_cmd
        sessao["comandos_feitos"] = ultimo_cmd - sessao.get("cmd_inicio", 0)
        self._salvar(ck)

        dt_inicio = datetime.fromisoformat(sessao["inicio"])
        duracao = agora - dt_inicio
        horas = duracao.seconds // 3600
        minutos = (duracao.seconds % 3600) // 60

        total_cmd = 0
        if fila_path and fila_path.exists():
            with open(fila_path, 'r') as f:
                total_cmd = json.load(f).get("total_comandos", 0)

        restantes = total_cmd - ultimo_cmd

        print(f"\n  🔴 SESSÃO #{len(sessoes)} ENCERRADA")
        print(f"     Duração: {horas}h{minutos:02d}min")
        print(f"     Comandos nesta sessão: {sessao['comandos_feitos']}")
        print(f"     Último comando: #{ultimo_cmd:03d}")

        if restantes > 0:
            print(f"\n  📋 PARA RETOMAR:")
            print(f"     Restam {restantes} comandos")
            print(f"     Próximo: COMANDO #{ultimo_cmd + 1:03d}")
        else:
            print(f"\n  ✅ MISSÃO COMPLETA!")
        print()

    def info(self, fila_path=None):
        ck = self._carregar()
        sessoes = ck.get("sessoes", [])
        ultimo_cmd = ck.get("ultimo_comando", 0)
        total_analisados = len(ck.get("processos_analisados", {}))

        total_cmd = 0
        total_proc = 0
        if fila_path and fila_path.exists():
            with open(fila_path, 'r') as f:
                fila = json.load(f)
                total_cmd = fila.get("total_comandos", 0)
                total_proc = fila.get("total_processos", 0)

        pct = (total_analisados / total_proc * 100) if total_proc else 0
        barra = "█" * int(pct // 2.5) + "░" * (40 - int(pct // 2.5))

        print(f"\n  [{barra}] {pct:.1f}%")
        print(f"  Processos: {total_analisados} / {total_proc}")
        print(f"  Comandos:  {ultimo_cmd} / {total_cmd}")

        if sessoes and not sessoes[-1].get("fim"):
            print(f"  🟢 Sessão ativa")
        else:
            print(f"  🔴 Sem sessão ativa")

        if ultimo_cmd < total_cmd:
            print(f"  ▶ Próximo: COMANDO #{ultimo_cmd + 1:03d}")
        elif total_cmd > 0:
            print(f"  ✅ Completo!")
        print()
