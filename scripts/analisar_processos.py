#!/usr/bin/env python3
"""
analisar_processos.py — Prepara fila de análise com checkpoint e controle de sessão.

GERA:
  - comandos_claude_code.txt  -> Comandos prontos para copiar no Claude Code
  - fila_analise.json         -> Fila completa com estado de cada processo
  - checkpoint.json           -> Estado atual (quais já foram analisados)

USO:
    python3 scripts/analisar_processos.py           # Gera fila e comandos
    python3 scripts/analisar_processos.py --status   # Mostra progresso atual
    python3 scripts/analisar_processos.py --reset    # Recomeça do zero
"""

import os
import csv
import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

DIR_TEXTOS = Path("textos_extraidos")
DIR_RESULTADOS = Path("resultados")
DIR_PROMPTS = Path("prompts")
CSV_PROCESSOS = "processos_crime_parados_mais_que_100_dias.csv"
CHECKPOINT_FILE = Path("checkpoint.json")
FILA_FILE = Path("fila_analise.json")
COMANDOS_FILE = Path("comandos_claude_code.txt")

DIR_RESULTADOS.mkdir(exist_ok=True)

CLASSE_PARA_PROMPT = {
    "APOrd": "prompt_APOrd.md",
    "IP": "prompt_IP.md",
    "TCO": "prompt_TCO.md",
    "Juri": "prompt_Juri.md",
    "APSum": "prompt_APSum.md",
    "APSumss": "prompt_APSumss.md",
}

BATCH_COM_PDF = 3
BATCH_SEM_PDF = 15


def calcular_urgencia(row):
    dias = int(row.get("Dias", 0))
    assunto = row.get("Assunto", "").lower()
    classe = row.get("Classe", "")
    criticos = ["homicídio", "latrocínio", "estupro", "vulnerável"]
    altos = ["tráfico", "roubo", "armas", "violência doméstica", "mulher", "medida protetiva", "descumprimento"]
    score = dias
    if any(kw in assunto for kw in criticos) or classe == "Juri":
        score += 2000
    elif any(kw in assunto for kw in altos):
        score += 1000
    if dias > 730:
        score += 500
    elif dias > 365:
        score += 300
    if score >= 1500:
        return score, "CRITICA"
    elif score >= 800:
        return score, "ALTA"
    elif score >= 400:
        return score, "MEDIA"
    else:
        return score, "BAIXA"


def num_para_arquivo(numero):
    return numero.replace('.', '_').replace('-', '_') + ".txt"


def carregar_checkpoint():
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


def salvar_checkpoint(ck):
    ck["ultima_atualizacao"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(ck, f, ensure_ascii=False, indent=2)


def mostrar_status():
    ck = carregar_checkpoint()
    total_analisados = len(ck.get("processos_analisados", {}))
    comandos_feitos = ck.get("comandos_concluidos", [])
    ultimo = ck.get("ultimo_comando", 0)

    total_comandos = 0
    total_processos = 0
    if FILA_FILE.exists():
        with open(FILA_FILE, 'r', encoding='utf-8') as f:
            fila = json.load(f)
            total_comandos = fila.get("total_comandos", 0)
            total_processos = fila.get("total_processos", 0)

    resultados_existentes = list(DIR_RESULTADOS.glob("analise_*.csv"))

    pct = (total_analisados / total_processos * 100) if total_processos else 0
    barra = "█" * int(pct // 2.5) + "░" * (40 - int(pct // 2.5))

    print()
    print("=" * 62)
    print("  STATUS DA ANÁLISE DE PROCESSOS CRIMINAIS")
    print("=" * 62)
    print(f"  Progresso: [{barra}] {pct:.1f}%")
    print(f"  Processos: {total_analisados} / {total_processos} analisados")
    print(f"  Comandos:  {len(comandos_feitos)} / {total_comandos} concluídos")
    print(f"  Arquivos:  {len(resultados_existentes)} em resultados/")
    print(f"  Atualizado: {ck.get('ultima_atualizacao', 'N/A')}")

    sessoes = ck.get("sessoes", [])
    if sessoes:
        print(f"\n  Histórico de sessões ({len(sessoes)} total):")
        for s in sessoes[-5:]:
            fim = s.get('fim', 'em andamento')
            print(f"    {s.get('inicio', '?')[:16]} → {fim[:16] if fim != 'em andamento' else fim}"
                  f"  ({s.get('comandos_feitos', 0)} cmds)")

    if ultimo < total_comandos:
        print(f"\n  ▶ RETOMAR DE: Comando #{ultimo + 1:03d}")
        print(f"    Abra comandos_claude_code.txt e procure:")
        print(f"    # === COMANDO {ultimo + 1:03d}")
        # Estimar tempo restante
        restantes = total_comandos - ultimo
        print(f"\n  ⏱️  Restam ~{restantes} comandos (~{restantes * 5}–{restantes * 8} min)")
    elif total_comandos > 0:
        print(f"\n  ✅ ANÁLISE COMPLETA! Rode:")
        print(f"     python3 scripts/consolidar.py")
    else:
        print(f"\n  ⚠️  Fila ainda não gerada. Rode:")
        print(f"     python3 scripts/analisar_processos.py")

    print("=" * 62)
    print()


def gerar_fila_e_comandos():
    processos_csv = {}
    with open(CSV_PROCESSOS, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            num = row.get('Número do Processo', '').strip()
            if num:
                processos_csv[num] = row
    print(f"  CSV: {len(processos_csv)} processos")

    txts = {f.name: f for f in DIR_TEXTOS.glob("*.txt")}
    print(f"  Textos extraídos: {len(txts)} arquivos")

    ck = carregar_checkpoint()
    ja_analisados = set(ck.get("processos_analisados", {}).keys())

    todos = []
    for num, dados in processos_csv.items():
        classe = dados.get("Classe", "OUTRO").strip()
        prompt = CLASSE_PARA_PROMPT.get(classe, "prompt_outros.md")
        score, urgencia = calcular_urgencia(dados)
        txt_nome = num_para_arquivo(num)
        txt_existe = (DIR_TEXTOS / txt_nome).exists()

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

    pendentes_com = sorted([p for p in todos if p["tem_pdf"] and not p["ja_analisado"]],
                           key=lambda x: -x["score"])
    pendentes_sem = sorted([p for p in todos if not p["tem_pdf"] and not p["ja_analisado"]],
                           key=lambda x: -x["score"])
    ja_feitos = [p for p in todos if p["ja_analisado"]]

    print(f"  Com PDF pendentes: {len(pendentes_com)}")
    print(f"  Sem PDF pendentes: {len(pendentes_sem)}")
    print(f"  Já analisados:     {len(ja_feitos)}")

    # === GERAR COMANDOS ===
    comandos = []
    cmd_num = 0

    # COM PDF: agrupar por prompt
    grupos_pdf = defaultdict(list)
    for p in pendentes_com:
        grupos_pdf[p["prompt"]].append(p)

    for prompt_file, grupo in sorted(grupos_pdf.items(), key=lambda x: -max(p["score"] for p in x[1])):
        for i in range(0, len(grupo), BATCH_COM_PDF):
            sub = grupo[i:i + BATCH_COM_PDF]
            cmd_num += 1

            arquivos = "\n".join(
                f"  - textos_extraidos/{p['txt_arquivo']}"
                f"  ({p['numero']} | {p['assunto']} | {p['dias_parado']}d | {p['urgencia']})"
                for p in sub
            )
            nums = " ".join(p["numero"] for p in sub)

            texto = f"""# === COMANDO {cmd_num:03d} === [{sub[0]['classe']}] [{len(sub)} com PDF] ===
# Processos: {nums}
# Ao concluir: python3 scripts/marcar_concluido.py {cmd_num} {nums}

Leia o prompt em prompts/{prompt_file}.
Analise os processos (leia CADA .txt completo):

{arquivos}

Para CADA processo: resumo com páginas, fase processual, diagnóstico,
próximo ato, modelo de despacho, fundamentação legal, prescrição.
Salve em resultados/analise_{cmd_num:03d}.csv"""

            comandos.append({"num": cmd_num, "texto": texto,
                             "processos": [p["numero"] for p in sub],
                             "tipo": "COM_PDF", "prompt": prompt_file})

    # SEM PDF
    if pendentes_sem:
        grupos_sem = defaultdict(list)
        for p in pendentes_sem:
            grupos_sem[p["prompt"]].append(p)

        for prompt_file, grupo in sorted(grupos_sem.items(), key=lambda x: -max(p["score"] for p in x[1])):
            for i in range(0, len(grupo), BATCH_SEM_PDF):
                sub = grupo[i:i + BATCH_SEM_PDF]
                cmd_num += 1

                tabela = "| Número | Classe | Assunto | Tarefa | Dias | Última Mov. |\n"
                tabela += "|--------|--------|---------|--------|------|------------|\n"
                for p in sub:
                    tabela += f"| {p['numero']} | {p['classe']} | {p['assunto']} | {p['tarefa'][:30]} | {p['dias_parado']} | {p['ultima_mov'][:40]} |\n"

                nums = " ".join(p["numero"] for p in sub)

                texto = f"""# === COMANDO {cmd_num:03d} === [{sub[0]['classe']}] [{len(sub)} SEM PDF — só CSV] ===
# Processos: {nums}
# Ao concluir: python3 scripts/marcar_concluido.py {cmd_num} {nums}

Leia prompts/{prompt_file}.
Analise com base APENAS nos dados do CSV (sem acesso aos autos):

{tabela}

Para CADA processo: próximo ato provável, modelo de despacho, fundamentação.
Indique que análise é LIMITADA. Salve em resultados/analise_{cmd_num:03d}.csv"""

                comandos.append({"num": cmd_num, "texto": texto,
                                 "processos": [p["numero"] for p in sub],
                                 "tipo": "SEM_PDF", "prompt": prompt_file})

    # === SALVAR ===
    with open(COMANDOS_FILE, 'w', encoding='utf-8') as f:
        f.write("# " + "=" * 60 + "\n")
        f.write("# COMANDOS PARA O CLAUDE CODE\n")
        f.write(f"# Gerado: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        f.write(f"# Total: {cmd_num} comandos | {len(pendentes_com)+len(pendentes_sem)} processos\n")
        f.write("# " + "=" * 60 + "\n")
        f.write("#\n")
        f.write("# COMO USAR:\n")
        f.write("# 1. cd projeto_final && claude\n")
        f.write("# 2. Cole UM comando por vez\n")
        f.write("# 3. Após cada comando, marque concluído (linha 'Ao concluir:')\n")
        f.write("# 4. Se sessão expirar: python3 scripts/analisar_processos.py --status\n")
        f.write("#    para ver onde parou e retomar\n")
        f.write("# " + "=" * 60 + "\n\n")

        for cmd in comandos:
            f.write(cmd["texto"])
            f.write("\n\n")

    fila = {
        "gerado_em": datetime.now().isoformat(),
        "total_processos": len(todos),
        "total_comandos": cmd_num,
        "pendentes_com_pdf": len(pendentes_com),
        "pendentes_sem_pdf": len(pendentes_sem),
        "ja_analisados": len(ja_feitos),
        "comandos": [{"num": c["num"], "processos": c["processos"],
                       "tipo": c["tipo"], "prompt": c["prompt"]} for c in comandos],
    }
    with open(FILA_FILE, 'w', encoding='utf-8') as f:
        json.dump(fila, f, ensure_ascii=False, indent=2)

    salvar_checkpoint(ck)

    total_cmds = cmd_num
    print(f"\n{'=' * 60}")
    print(f"  {total_cmds} comandos gerados → {COMANDOS_FILE}")
    print(f"  Estimativa: {total_cmds*5//60}h{total_cmds*5%60:02d} ~ {total_cmds*8//60}h{total_cmds*8%60:02d}")
    print(f"  Sessões de ~4h: ~{(total_cmds*7//60)//4 + 1}")
    print(f"\n  ▶ COMECE: abra {COMANDOS_FILE} e cole COMANDO 001 no Claude Code")
    print(f"{'=' * 60}")


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--status":
            mostrar_status()
        elif arg == "--reset":
            for f in [CHECKPOINT_FILE, FILA_FILE, COMANDOS_FILE]:
                if f.exists():
                    f.unlink()
            print("Checkpoint resetado.")
        elif arg == "--help":
            print(__doc__)
        else:
            print(f"Argumento desconhecido: {arg}")
            print("Use: --status, --reset, ou --help")
    else:
        print("=" * 60)
        print("GERAÇÃO DE FILA DE ANÁLISE")
        print("=" * 60)
        gerar_fila_e_comandos()


if __name__ == "__main__":
    main()
