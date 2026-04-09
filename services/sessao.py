#!/usr/bin/env python3
"""
sessao.py — Registra início/fim de sessão no checkpoint.

USO:
    python3 scripts/sessao.py inicio    # Registra início de sessão
    python3 scripts/sessao.py fim       # Registra fim de sessão
    python3 scripts/sessao.py info      # Mostra informações da sessão + limite de uso

O Claude Code (plano Pro) tem limite de uso. Este script ajuda a:
- Rastrear quanto tempo cada sessão durou
- Saber quantos comandos foram feitos por sessão
- Planejar quando retomar (geralmente o limite reseta a cada ~5h)
"""

import json
import sys
from pathlib import Path
from datetime import datetime

CHECKPOINT_FILE = Path("checkpoint.json")


def carregar():
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "criado_em": datetime.now().isoformat(),
        "ultima_atualizacao": datetime.now().isoformat(),
        "processos_analisados": {},
        "comandos_concluidos": [],
        "ultimo_comando": 0,
        "sessoes": []
    }


def salvar(ck):
    ck["ultima_atualizacao"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(ck, f, ensure_ascii=False, indent=2)


def inicio():
    ck = carregar()
    agora = datetime.now().isoformat()
    ultimo_cmd = ck.get("ultimo_comando", 0)

    sessao = {
        "inicio": agora,
        "fim": None,
        "cmd_inicio": ultimo_cmd,
        "cmd_fim": None,
        "comandos_feitos": 0
    }
    ck.setdefault("sessoes", []).append(sessao)
    salvar(ck)

    num_sessao = len(ck["sessoes"])
    print(f"\n  🟢 SESSÃO #{num_sessao} INICIADA")
    print(f"     Horário: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"     Retomar de: Comando #{ultimo_cmd + 1:03d}")
    print(f"\n     Dica: quando sentir que o limite está próximo,")
    print(f"     rode: python3 scripts/sessao.py fim")
    print()


def fim():
    ck = carregar()
    sessoes = ck.get("sessoes", [])

    if not sessoes or sessoes[-1].get("fim"):
        print("  ⚠️  Nenhuma sessão aberta. Rode 'python3 scripts/sessao.py inicio' primeiro.")
        return

    agora = datetime.now().isoformat()
    ultimo_cmd = ck.get("ultimo_comando", 0)
    sessao = sessoes[-1]
    sessao["fim"] = agora
    sessao["cmd_fim"] = ultimo_cmd
    sessao["comandos_feitos"] = ultimo_cmd - sessao.get("cmd_inicio", 0)

    salvar(ck)

    # Calcular duração
    dt_inicio = datetime.fromisoformat(sessao["inicio"])
    dt_fim = datetime.fromisoformat(agora)
    duracao = dt_fim - dt_inicio
    horas = duracao.seconds // 3600
    minutos = (duracao.seconds % 3600) // 60

    # Carregar total para estimar
    fila_path = Path("fila_analise.json")
    total_cmd = 0
    if fila_path.exists():
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
        print(f"     Estimativa: ~{restantes*5}-{restantes*8} min restantes")
        print(f"\n  ⏰ O limite do Claude Code geralmente reseta em ~5 horas.")
        print(f"     Volte por volta das {(dt_fim.hour + 5) % 24}:{dt_fim.strftime('%M')} para continuar.")
    else:
        print(f"\n  🎉 ANÁLISE COMPLETA!")
        print(f"     Rode: python3 scripts/consolidar.py")

    print()


def info():
    ck = carregar()
    sessoes = ck.get("sessoes", [])
    ultimo_cmd = ck.get("ultimo_comando", 0)
    total_analisados = len(ck.get("processos_analisados", {}))

    fila_path = Path("fila_analise.json")
    total_cmd = 0
    total_proc = 0
    if fila_path.exists():
        with open(fila_path, 'r') as f:
            fila = json.load(f)
            total_cmd = fila.get("total_comandos", 0)
            total_proc = fila.get("total_processos", 0)

    pct = (total_analisados / total_proc * 100) if total_proc else 0
    barra = "█" * int(pct // 2.5) + "░" * (40 - int(pct // 2.5))

    print(f"\n  ┌{'─'*58}┐")
    print(f"  │  ANÁLISE DE PROCESSOS CRIMINAIS — PAINEL DE CONTROLE    │")
    print(f"  ├{'─'*58}┤")
    print(f"  │  [{barra}] {pct:5.1f}%  │")
    print(f"  │  Processos: {total_analisados:>3} / {total_proc:<3}  │  Comandos: {ultimo_cmd:>3} / {total_cmd:<3}       │")
    print(f"  ├{'─'*58}┤")

    # Sessão atual
    if sessoes and not sessoes[-1].get("fim"):
        s = sessoes[-1]
        dt = datetime.fromisoformat(s["inicio"])
        dur = datetime.now() - dt
        m = dur.seconds // 60
        cmds = ultimo_cmd - s.get("cmd_inicio", 0)
        print(f"  │  🟢 Sessão #{len(sessoes)} ativa há {m} min ({cmds} cmds feitos)     │")
    else:
        print(f"  │  🔴 Sem sessão ativa                                    │")

    print(f"  │  Último comando: #{ultimo_cmd:03d}                                 │")

    if ultimo_cmd < total_cmd:
        print(f"  │  ▶ Próximo: #{ultimo_cmd+1:03d}                                      │")
        restantes = total_cmd - ultimo_cmd
        print(f"  │  Restam: {restantes} cmds (~{restantes*5}-{restantes*8} min)                     │")
    else:
        print(f"  │  ✅ Análise completa!                                    │")

    print(f"  └{'─'*58}┘")

    # Histórico
    if sessoes:
        print(f"\n  Histórico ({len(sessoes)} sessões):")
        for i, s in enumerate(sessoes, 1):
            inicio = datetime.fromisoformat(s["inicio"]).strftime("%d/%m %H:%M")
            fim_str = datetime.fromisoformat(s["fim"]).strftime("%H:%M") if s.get("fim") else "ativa"
            cmds = s.get("comandos_feitos", "?")
            print(f"    #{i}: {inicio} → {fim_str}  ({cmds} cmds)")

    print()


def main():
    if len(sys.argv) < 2:
        print("USO:")
        print("  python3 scripts/sessao.py inicio  — Registra início")
        print("  python3 scripts/sessao.py fim      — Registra fim")
        print("  python3 scripts/sessao.py info     — Mostra painel")
        return

    cmd = sys.argv[1].lower()
    if cmd == "inicio":
        inicio()
    elif cmd == "fim":
        fim()
    elif cmd == "info":
        info()
    else:
        print(f"Comando desconhecido: {cmd}")


if __name__ == "__main__":
    main()
