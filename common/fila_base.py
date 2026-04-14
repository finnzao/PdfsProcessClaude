#!/usr/bin/env python3
"""fila_base.py — Gera fila de comandos pro Claude Code, ordenada por urgência."""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from common.utils import carregar_csv_processos, num_para_arquivo, calcular_urgencia, DIR_TEXTOS, agora_iso


class FilaBase:
    SERVICE_NAME = "base"
    BATCH_COM_PDF = 3
    BATCH_SEM_PDF = 15
    CLASSE_PARA_PROMPT = {}

    def __init__(self, service_dir: Path):
        self.service_dir = service_dir
        self.checkpoint_path = service_dir / "checkpoint.json"
        self.fila_path = service_dir / "fila.json"
        self.comandos_path = service_dir / "comandos_claude_code.txt"
        self.resultados_dir = service_dir / "resultados"
        self.resultados_dir.mkdir(exist_ok=True)

    def _ck(self):
        if self.checkpoint_path.exists(): return json.loads(self.checkpoint_path.read_text(encoding='utf-8'))
        return {"processos_analisados": {}, "comandos_concluidos": [], "ultimo_comando": 0}

    def _prompt(self, classe):
        return self.CLASSE_PARA_PROMPT.get(classe, self._prompt_default())

    def _prompt_default(self): return "prompt_outros.md"

    def gerar_comando_com_pdf(self, n, procs, prompt): raise NotImplementedError
    def gerar_comando_sem_pdf(self, n, procs, prompt): raise NotImplementedError

    def gerar(self):
        """Monta todos os comandos e salva em .txt e .json."""
        csv_procs = carregar_csv_processos()
        print(f"  CSV: {len(csv_procs)} processos")

        txts = {f.stem: f for f in DIR_TEXTOS.iterdir() if f.suffix in ('.txt','.md')} if DIR_TEXTOS.exists() else {}
        print(f"  Textos: {len(txts)}")

        ja = set(self._ck().get("processos_analisados", {}).keys())
        todos = []
        for num, d in csv_procs.items():
            cl = d.get("Classe","").strip()
            sc, urg = calcular_urgencia(d)
            tn = num_para_arquivo(num)
            todos.append({"numero": num, "classe": cl, "assunto": d.get("Assunto",""),
                "tarefa": d.get("Tarefa",""), "dias_parado": int(d.get("Dias",0)),
                "ultima_mov": d.get("Última Movimentação",""), "urgencia": urg, "score": sc,
                "prompt": self._prompt(cl), "tem_pdf": Path(tn).stem in txts,
                "txt_arquivo": tn, "ja": num in ja})

        com = sorted([p for p in todos if p["tem_pdf"] and not p["ja"]], key=lambda x: -x["score"])
        sem = sorted([p for p in todos if not p["tem_pdf"] and not p["ja"]], key=lambda x: -x["score"])
        print(f"  Pendentes: {len(com)} com PDF, {len(sem)} sem")

        cmds = []
        cn = 0
        for prompt, grupo in sorted(defaultdict(list, {p["prompt"]: [] for p in com}).items()):
            for p in com:
                if p["prompt"] == prompt: grupo.append(p)
            for i in range(0, len(grupo), self.BATCH_COM_PDF):
                cn += 1
                cmds.append({"num": cn, "texto": self.gerar_comando_com_pdf(cn, grupo[i:i+self.BATCH_COM_PDF], prompt),
                    "processos": [p["numero"] for p in grupo[i:i+self.BATCH_COM_PDF]], "tipo": "COM_PDF"})

        for prompt, grupo in sorted(defaultdict(list, {p["prompt"]: [] for p in sem}).items()):
            for p in sem:
                if p["prompt"] == prompt: grupo.append(p)
            for i in range(0, len(grupo), self.BATCH_SEM_PDF):
                cn += 1
                cmds.append({"num": cn, "texto": self.gerar_comando_sem_pdf(cn, grupo[i:i+self.BATCH_SEM_PDF], prompt),
                    "processos": [p["numero"] for p in grupo[i:i+self.BATCH_SEM_PDF]], "tipo": "SEM_PDF"})

        with open(self.comandos_path, 'w', encoding='utf-8') as f:
            f.write(f"# {self.SERVICE_NAME} — {cn} comandos — {datetime.now():%d/%m/%Y %H:%M}\n\n")
            for c in cmds: f.write(c["texto"] + "\n\n")

        self.fila_path.write_text(json.dumps({"gerado_em": agora_iso(), "service": self.SERVICE_NAME,
            "total_processos": len(todos), "total_comandos": cn,
            "comandos": [{"num": c["num"], "processos": c["processos"], "tipo": c["tipo"]} for c in cmds]
        }, ensure_ascii=False, indent=2), encoding='utf-8')

        print(f"\n  {cn} comandos → {self.comandos_path}")

    def status(self):
        """Barra de progresso."""
        ck = self._ck()
        done = len(ck.get("processos_analisados", {}))
        ult = ck.get("ultimo_comando", 0)
        tc = tp = 0
        if self.fila_path.exists():
            fl = json.loads(self.fila_path.read_text())
            tc, tp = fl.get("total_comandos",0), fl.get("total_processos",0)
        pct = done/tp*100 if tp else 0
        bar = "█" * int(pct//2.5) + "░" * (40-int(pct//2.5))
        print(f"\n  [{bar}] {pct:.1f}%\n  Processos: {done}/{tp} | Comandos: {ult}/{tc}")
        if ult < tc: print(f"  ▶ Próximo: #{ult+1:03d}")
        elif tc: print("  ✅ COMPLETO!")
        print()
