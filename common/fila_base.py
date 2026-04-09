#!/usr/bin/env python3
"""
fila_base.py — Classe base para geração de filas de comandos.
Cada service herda e customiza: prompt, formato do comando, batch size.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from common.utils import (
    carregar_csv_processos, num_para_arquivo, calcular_urgencia,
    DIR_TEXTOS, agora_iso
)


class FilaBase:
    """Classe base para geração de fila de comandos do Claude Code."""

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
        self.prompts_dir = service_dir / "prompts"
        self.resultados_dir.mkdir(exist_ok=True)

    def _carregar_checkpoint(self):
        if self.checkpoint_path.exists():
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"processos_analisados": {}, "comandos_concluidos": [],
                "ultimo_comando": 0, "sessoes": []}

    def _prompt_para_classe(self, classe):
        return self.CLASSE_PARA_PROMPT.get(classe, self._prompt_default())

    def _prompt_default(self):
        return "prompt_outros.md"

    def gerar_comando_com_pdf(self, cmd_num, processos, prompt_file):
        """Override nos services para customizar o formato do comando."""
        raise NotImplementedError

    def gerar_comando_sem_pdf(self, cmd_num, processos, prompt_file):
        """Override nos services para customizar o formato do comando."""
        raise NotImplementedError

    def gerar(self):
        processos_csv = carregar_csv_processos()
        print(f"  CSV: {len(processos_csv)} processos")

        txts = {f.stem: f for f in DIR_TEXTOS.iterdir()
                if f.suffix in ('.txt', '.md')} if DIR_TEXTOS.exists() else {}
        print(f"  Textos extraídos: {len(txts)} arquivos")

        ck = self._carregar_checkpoint()
        ja_analisados = set(ck.get("processos_analisados", {}).keys())

        todos = []
        for num, dados in processos_csv.items():
            classe = dados.get("Classe", "OUTRO").strip()
            prompt = self._prompt_para_classe(classe)
            score, urgencia = calcular_urgencia(dados)
            txt_nome = num_para_arquivo(num)
            txt_stem = Path(txt_nome).stem
            txt_existe = txt_stem in txts

            todos.append({
                "numero": num, "classe": classe,
                "assunto": dados.get("Assunto", ""),
                "tarefa": dados.get("Tarefa", ""),
                "dias_parado": int(dados.get("Dias", 0)),
                "ultima_mov": dados.get("Última Movimentação", ""),
                "data_mov": dados.get("Data Último Movimento", ""),
                "urgencia": urgencia, "score": score,
                "prompt": prompt, "tem_pdf": txt_existe,
                "txt_arquivo": txt_nome,
                "ja_analisado": num in ja_analisados,
            })

        pendentes_com = sorted(
            [p for p in todos if p["tem_pdf"] and not p["ja_analisado"]],
            key=lambda x: -x["score"])
        pendentes_sem = sorted(
            [p for p in todos if not p["tem_pdf"] and not p["ja_analisado"]],
            key=lambda x: -x["score"])

        print(f"  Com PDF pendentes: {len(pendentes_com)}")
        print(f"  Sem PDF pendentes: {len(pendentes_sem)}")

        comandos = []
        cmd_num = 0

        # COM PDF: agrupar por prompt
        grupos = defaultdict(list)
        for p in pendentes_com:
            grupos[p["prompt"]].append(p)

        for prompt_file, grupo in sorted(grupos.items(),
                key=lambda x: -max(p["score"] for p in x[1])):
            for i in range(0, len(grupo), self.BATCH_COM_PDF):
                sub = grupo[i:i + self.BATCH_COM_PDF]
                cmd_num += 1
                texto = self.gerar_comando_com_pdf(cmd_num, sub, prompt_file)
                comandos.append({
                    "num": cmd_num, "texto": texto,
                    "processos": [p["numero"] for p in sub],
                    "tipo": "COM_PDF", "prompt": prompt_file
                })

        # SEM PDF
        if pendentes_sem:
            grupos_sem = defaultdict(list)
            for p in pendentes_sem:
                grupos_sem[p["prompt"]].append(p)

            for prompt_file, grupo in sorted(grupos_sem.items(),
                    key=lambda x: -max(p["score"] for p in x[1])):
                for i in range(0, len(grupo), self.BATCH_SEM_PDF):
                    sub = grupo[i:i + self.BATCH_SEM_PDF]
                    cmd_num += 1
                    texto = self.gerar_comando_sem_pdf(cmd_num, sub, prompt_file)
                    comandos.append({
                        "num": cmd_num, "texto": texto,
                        "processos": [p["numero"] for p in sub],
                        "tipo": "SEM_PDF", "prompt": prompt_file
                    })

        # Salvar comandos
        with open(self.comandos_path, 'w', encoding='utf-8') as f:
            f.write(f"# {'=' * 60}\n")
            f.write(f"# COMANDOS — {self.SERVICE_NAME}\n")
            f.write(f"# Gerado: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write(f"# Total: {cmd_num} comandos\n")
            f.write(f"# {'=' * 60}\n\n")
            for cmd in comandos:
                f.write(cmd["texto"])
                f.write("\n\n")

        # Salvar fila
        fila = {
            "gerado_em": agora_iso(),
            "service": self.SERVICE_NAME,
            "total_processos": len(todos),
            "total_comandos": cmd_num,
            "pendentes_com_pdf": len(pendentes_com),
            "pendentes_sem_pdf": len(pendentes_sem),
            "comandos": [{"num": c["num"], "processos": c["processos"],
                          "tipo": c["tipo"]} for c in comandos],
        }
        with open(self.fila_path, 'w', encoding='utf-8') as f:
            json.dump(fila, f, ensure_ascii=False, indent=2)

        print(f"\n  {cmd_num} comandos gerados → {self.comandos_path}")
        print(f"  ▶ Abra o arquivo e cole COMANDO 001 no Claude Code")

    def status(self):
        ck = self._carregar_checkpoint()
        total_analisados = len(ck.get("processos_analisados", {}))
        ultimo = ck.get("ultimo_comando", 0)

        total_cmd = 0
        total_proc = 0
        if self.fila_path.exists():
            with open(self.fila_path, 'r') as f:
                fila = json.load(f)
                total_cmd = fila.get("total_comandos", 0)
                total_proc = fila.get("total_processos", 0)

        pct = (total_analisados / total_proc * 100) if total_proc else 0
        barra = "█" * int(pct // 2.5) + "░" * (40 - int(pct // 2.5))

        print(f"\n  [{barra}] {pct:.1f}%")
        print(f"  Processos: {total_analisados} / {total_proc}")
        print(f"  Comandos:  {ultimo} / {total_cmd}")

        resultados = list(self.resultados_dir.glob("*"))
        print(f"  Arquivos resultado: {len(resultados)}")

        if ultimo < total_cmd:
            restantes = total_cmd - ultimo
            print(f"\n  ▶ Próximo: COMANDO #{ultimo + 1:03d}")
            print(f"  Restam: {restantes} comandos")
        elif total_cmd > 0:
            print(f"\n  ✅ COMPLETO!")
        print()
