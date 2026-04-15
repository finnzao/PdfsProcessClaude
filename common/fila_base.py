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

    # ── Mapeamento de filtro → classes do CSV ──
    FILTRO_CLASSES = {
        "TCO":     ["Termo Circunstanciado", "TCO"],
        "IP":      ["Inquérito Policial", "IP"],
        "APOrd":   ["Ação Penal - Procedimento Ordinário", "APOrd"],
        "APSum":   ["Ação Penal - Procedimento Sumário", "APSum"],
        "APSumss": ["Ação Penal - Procedimento Sumaríssimo", "APSumss"],
        "Juri":    ["Tribunal do Júri", "Juri", "Júri", "Ação Penal - Procedimento do Tribunal do Júri"],
    }

    def _normalizar_classe(self, classe_csv: str) -> str:
        """Converte nome do CSV para código interno."""
        cl = classe_csv.strip()
        for codigo, nomes in self.FILTRO_CLASSES.items():
            for nome in nomes:
                if nome.lower() in cl.lower() or cl.lower() in nome.lower():
                    return codigo
        return cl

    def _filtrar_por_classes(self, processos: dict, filtros: list) -> dict:
        """Filtra processos por uma ou mais classes processuais."""
        if not filtros:
            return processos

        # Montar lista unificada de nomes aceitos
        nomes_aceitos = []
        for filtro in filtros:
            filtro_upper = filtro.upper().strip()
            encontrou = False
            for codigo, nomes in self.FILTRO_CLASSES.items():
                if codigo.upper() == filtro_upper:
                    nomes_aceitos.extend(n.lower() for n in nomes)
                    encontrou = True
                    break
            if not encontrou:
                nomes_aceitos.append(filtro.lower())

        filtrado = {}
        for num, row in processos.items():
            cl = row.get("Classe", "").strip().lower()
            if any(nome in cl or cl in nome for nome in nomes_aceitos):
                filtrado[num] = row

        return filtrado

    def _parse_filtro(self, args) -> list:
        """Converte args em lista de classes.

        Aceita:
          ["TCO"]              -> ["TCO"]
          ["TCO", "IP"]        -> ["TCO", "IP"]
          ["TCO,IP"]           -> ["TCO", "IP"]
          ["TCO+IP"]           -> ["TCO", "IP"]
          ["TCO", "IP", "Juri"]-> ["TCO", "IP", "Juri"]
        """
        if not args:
            return []
        # Juntar tudo, separar por vírgula, +, ou espaço
        import re
        raw = " ".join(args) if isinstance(args, list) else str(args)
        partes = re.split(r'[,+\s]+', raw)
        return [p.strip() for p in partes if p.strip()]

    def gerar(self, filtro_classe=None):
        """Monta todos os comandos e salva em .txt e .json.

        filtro_classe: str, list, ou None.
          str  -> uma classe ("TCO") ou várias separadas por vírgula/+  ("TCO,IP")
          list -> ["TCO", "IP"]
          None -> todas as classes
        """
        # Normalizar filtro para lista
        if isinstance(filtro_classe, str):
            filtros = self._parse_filtro([filtro_classe])
        elif isinstance(filtro_classe, list):
            filtros = self._parse_filtro(filtro_classe)
        else:
            filtros = []

        csv_procs = carregar_csv_processos()
        print(f"  CSV: {len(csv_procs)} processos")

        if filtros:
            label_filtro = "+".join(filtros)
            csv_procs = self._filtrar_por_classes(csv_procs, filtros)
            print(f"  Filtro [{label_filtro}]: {len(csv_procs)} processos")
            if not csv_procs:
                print(f"  Nenhum processo encontrado para classe(s): {label_filtro}")
                print(f"  Classes disponíveis: {', '.join(self.FILTRO_CLASSES.keys())}")
                return
        else:
            label_filtro = ""

        txts = {f.stem: f for f in DIR_TEXTOS.iterdir() if f.suffix in ('.txt','.md')} if DIR_TEXTOS.exists() else {}
        print(f"  Textos: {len(txts)}")

        ja = set(self._ck().get("processos_analisados", {}).keys())
        todos = []
        for num, d in csv_procs.items():
            cl = d.get("Classe","").strip()
            cl_codigo = self._normalizar_classe(cl)
            sc, urg = calcular_urgencia(d)
            tn = num_para_arquivo(num)
            todos.append({"numero": num, "classe": cl_codigo, "assunto": d.get("Assunto",""),
                "tarefa": d.get("Tarefa",""), "dias_parado": int(d.get("Dias",0)),
                "ultima_mov": d.get("Última Movimentação",""), "urgencia": urg, "score": sc,
                "prompt": self._prompt(cl_codigo), "tem_pdf": Path(tn).stem in txts,
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

        # Sufixo no nome do arquivo se filtrado
        sufixo = f"_{label_filtro.lower()}" if label_filtro else ""

        comandos_path = self.service_dir / f"comandos_claude_code{sufixo}.txt"
        fila_path = self.service_dir / f"fila{sufixo}.json"

        with open(comandos_path, 'w', encoding='utf-8') as f:
            label_header = f" [{label_filtro}]" if label_filtro else ""
            f.write(f"# {self.SERVICE_NAME}{label_header} — {cn} comandos — {datetime.now():%d/%m/%Y %H:%M}\n\n")
            for c in cmds: f.write(c["texto"] + "\n\n")

        fila_path.write_text(json.dumps({"gerado_em": agora_iso(), "service": self.SERVICE_NAME,
            "filtro_classe": label_filtro or "TODAS",
            "total_processos": len(todos), "total_comandos": cn,
            "comandos": [{"num": c["num"], "processos": c["processos"], "tipo": c["tipo"]} for c in cmds]
        }, ensure_ascii=False, indent=2), encoding='utf-8')

        # Copiar para nomes padrão para compatibilidade com auto_analisar.py
        if label_filtro:
            import shutil
            shutil.copy2(comandos_path, self.comandos_path)
            shutil.copy2(fila_path, self.fila_path)

        print(f"\n  {cn} comandos -> {comandos_path}")

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
        bar = "#" * int(pct//2.5) + "-" * (40-int(pct//2.5))
        print(f"\n  [{bar}] {pct:.1f}%\n  Processos: {done}/{tp} | Comandos: {ult}/{tc}")
        if ult < tc: print(f"  > Proximo: #{ult+1:03d}")
        elif tc: print("  COMPLETO!")
        print()
