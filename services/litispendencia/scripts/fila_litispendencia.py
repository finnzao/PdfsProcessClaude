#!/usr/bin/env python3
"""
services/litispendencia/scripts/fila_litispendencia.py

Gera fila de comandos para o Claude Code analisar grupos de
litispendência a partir da planilha xlsx do filtro pré-classificador.

Estratégia adaptativa:
  - Grupos pequenos (≤3 procs): empacotados em CMDs com até 6 procs no total
  - Grupos grandes (≥6 procs): isolados, 1 grupo por CMD
  - Grupos médios (4-5 procs): isolados também

Salva (no padrão do projeto):
  services/litispendencia/fila.json
  services/litispendencia/comandos_claude_code.txt

Pula grupos já listados em controle_grupos.json (a menos que --forcar).

Uso:
    python -m services.litispendencia.scripts.fila_litispendencia
    python -m services.litispendencia.scripts.fila_litispendencia --xlsx files/litispendencia_2.xlsx
    python -m services.litispendencia.scripts.fila_litispendencia --abas "⭐ Litispendência,⚠ Coisa Julgada"
    python -m services.litispendencia.scripts.fila_litispendencia --forcar
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from common.utils import DIR_FILES, agora_iso

SERVICE_DIR = RAIZ / "services" / "litispendencia"
FILA_PATH = SERVICE_DIR / "fila.json"
CMDS_PATH = SERVICE_DIR / "comandos_claude_code.txt"
CONTROLE_PATH = SERVICE_DIR / "controle_grupos.json"
TEXTOS_DIR = RAIZ / "textos_extraidos"

# Empacotamento adaptativo
ALVO_PROCS_POR_CMD = 6       # alvo para grupos pequenos
LIMITE_GRUPO_GRANDE = 6      # 6+ procs = sempre isolado

# Mapa de aba → prefixo do group_id
PREFIXO_ABA = {
    "⭐ Litispendência": "lit",
    "⚠ Coisa Julgada": "cj",
    "Filtro Estrito": "estrito",
    "Filtro Médio": "medio",
    "Filtro Amplo": "amplo",
}

ABAS_DEFAULT = ["⭐ Litispendência", "⚠ Coisa Julgada"]


def carregar_controle():
    if CONTROLE_PATH.exists():
        try:
            return json.loads(CONTROLE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ⚠️  {CONTROLE_PATH.name} corrompido — começando do zero")
    return {
        "atualizado_em": agora_iso(),
        "total_analisados": 0,
        "grupos": {},
    }


def num_para_md(numero_cnj):
    """0001234-56.2024.8.05.0216 → 0001234_56_2024_8_05_0216.md"""
    return numero_cnj.replace(".", "_").replace("-", "_") + ".md"


def md_existe(numero_cnj):
    return (TEXTOS_DIR / num_para_md(numero_cnj)).exists()


def ler_xlsx(xlsx_path: Path, abas: list[str]) -> list[dict]:
    """Lê grupos das abas pedidas, retorna lista normalizada.

    Cada item: {
      'group_id': 'lit_001',
      'aba_origem': '⭐ Litispendência',
      'processos': ['0001234-...', ...],
      'n_processos': N,
      'partes_amostra': 'NOME (autor) vs NOME (réu)' (opcional),
      'classe_amostra': '...' (opcional),
      'assunto_amostra': '...' (opcional)
    }
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("  ✗ openpyxl não instalado. Rode: pip install openpyxl")
        sys.exit(1)

    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    grupos = []
    contadores = {}

    re_cnj = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")

    for aba_nome in abas:
        if aba_nome not in wb.sheetnames:
            print(f"  ⚠️  Aba não encontrada: {aba_nome}")
            continue

        ws = wb[aba_nome]
        prefixo = PREFIXO_ABA.get(aba_nome, "grp")
        contadores.setdefault(prefixo, 0)

        # Detecta cabeçalho lendo primeira linha
        primeira_linha = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not primeira_linha:
            continue
        cabecalho = [str(c).strip() if c else "" for c in primeira_linha]

        # Procura colunas relevantes (heurística: a aba tem múltiplas colunas
        # de processo OU uma coluna "processos" concatenada)
        col_processos_unica = None
        cols_processos_indiv = []
        col_partes = None
        col_classe = None
        col_assunto = None

        for i, col in enumerate(cabecalho):
            col_low = col.lower()
            if col_low in ("processos", "numeros_processos", "lista_processos"):
                col_processos_unica = i
            elif col_low.startswith("processo") or col_low.startswith("numero"):
                cols_processos_indiv.append(i)
            elif "parte" in col_low:
                col_partes = i
            elif "classe" in col_low:
                col_classe = i
            elif "assunto" in col_low:
                col_assunto = i

        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or all(c is None for c in row):
                continue

            # Extrair lista de processos do row
            cnjs = []
            if col_processos_unica is not None:
                celula = row[col_processos_unica]
                if celula:
                    cnjs = re_cnj.findall(str(celula))
            elif cols_processos_indiv:
                for i in cols_processos_indiv:
                    if i < len(row) and row[i]:
                        encontrados = re_cnj.findall(str(row[i]))
                        cnjs.extend(encontrados)
            else:
                # Fallback: varre todas as células procurando CNJs
                for cel in row:
                    if cel:
                        cnjs.extend(re_cnj.findall(str(cel)))

            # Dedup preservando ordem
            vistos = set()
            cnjs_unicos = []
            for c in cnjs:
                if c not in vistos:
                    vistos.add(c)
                    cnjs_unicos.append(c)

            if len(cnjs_unicos) < 2:
                continue  # grupo tem que ter ao menos 2 processos

            contadores[prefixo] += 1
            group_id = f"{prefixo}_{contadores[prefixo]:03d}"

            grupos.append({
                "group_id": group_id,
                "aba_origem": aba_nome,
                "processos": cnjs_unicos,
                "n_processos": len(cnjs_unicos),
                "partes_amostra": str(row[col_partes]).strip() if col_partes is not None and col_partes < len(row) and row[col_partes] else "",
                "classe_amostra": str(row[col_classe]).strip() if col_classe is not None and col_classe < len(row) and row[col_classe] else "",
                "assunto_amostra": str(row[col_assunto]).strip() if col_assunto is not None and col_assunto < len(row) and row[col_assunto] else "",
            })

    wb.close()
    return grupos


def empacotar_adaptativo(grupos: list[dict]) -> list[list[dict]]:
    """Empacota grupos em CMDs respeitando ALVO_PROCS_POR_CMD.

    Grupos grandes (≥ LIMITE_GRUPO_GRANDE) sempre isolados.
    Grupos pequenos empilhados até ALVO_PROCS_POR_CMD processos.
    """
    cmds = []
    buffer = []
    procs_buffer = 0

    for g in grupos:
        n = g["n_processos"]

        # Grupo grande: flush buffer + grupo isolado
        if n >= LIMITE_GRUPO_GRANDE:
            if buffer:
                cmds.append(buffer)
                buffer = []
                procs_buffer = 0
            cmds.append([g])
            continue

        # Grupo médio/pequeno: cabe no buffer?
        if procs_buffer + n > ALVO_PROCS_POR_CMD and buffer:
            cmds.append(buffer)
            buffer = []
            procs_buffer = 0

        buffer.append(g)
        procs_buffer += n

    if buffer:
        cmds.append(buffer)

    return cmds


def gerar_texto_cmd(num_cmd: int, grupos_do_cmd: list[dict]) -> str:
    """Gera o texto de um CMD com 1+ grupos."""
    group_ids = " ".join(g["group_id"] for g in grupos_do_cmd)
    n_procs_total = sum(g["n_processos"] for g in grupos_do_cmd)

    # Tabela de grupos no comando
    linhas_tabela = []
    for g in grupos_do_cmd:
        for cnj in g["processos"]:
            existe = "✓" if md_existe(cnj) else "✗"
            linhas_tabela.append(
                f"  {g['group_id']:<12} | {cnj} | md={existe}"
            )
        if g.get("partes_amostra"):
            linhas_tabela.append(f"  {'':12}   partes: {g['partes_amostra'][:80]}")
        if g.get("classe_amostra") or g.get("assunto_amostra"):
            ca = g.get("classe_amostra", "")
            ass = g.get("assunto_amostra", "")
            linhas_tabela.append(f"  {'':12}   classe/assunto: {ca} / {ass}")
        linhas_tabela.append("")

    tabela = "\n".join(linhas_tabela).rstrip()

    # Lista de arquivos .md a ler
    todos_cnjs = []
    for g in grupos_do_cmd:
        todos_cnjs.extend(g["processos"])
    todos_cnjs_unicos = list(dict.fromkeys(todos_cnjs))  # dedup preservando ordem

    arquivos = " ".join(
        f"textos_extraidos/{num_para_md(c)}"
        for c in todos_cnjs_unicos
        if md_existe(c)
    )

    return f"""# === CMD {num_cmd:03d} [LITISPENDENCIA] [{len(grupos_do_cmd)} grupo(s), {n_procs_total} proc(s)] ===
# Grupos: {group_ids}
# Ao concluir: python run.py litispendencia marcar {num_cmd} {group_ids}

Leia services/litispendencia/prompts/prompt_litispendencia.md e siga TODAS
as regras dele, em especial:
  - Salvamento INCREMENTAL após cada grupo (não só no fim do CMD)
  - Pular grupos já listados em controle_grupos.json
  - Distinguir rótulo (classe+assunto+partes) de causa de pedir
  - Múltiplos pares possíveis dentro do mesmo grupo grande

Grupos a analisar (NESTA ORDEM):

{tabela}

Arquivos .md disponíveis para leitura:
{arquivos}

Para CADA grupo (na ordem acima):

1. Ler services/litispendencia/controle_grupos.json — pular se group_id já presente
2. Ler todos os .md disponíveis do grupo (alguns podem faltar)
3. Comparar partes, classe, assunto E causa de pedir
4. Salvar services/litispendencia/resultados/grupos/grupo_<group_id>.json
   conforme schema do prompt
5. Atualizar controle_grupos.json com o group_id
6. SÓ ENTÃO ir ao próximo grupo

LEMBRETES CRÍTICOS:
- Litispendência exige partes + pedido + CAUSA DE PEDIR idênticos
- Dois CumSenFaz entre as mesmas partes podem executar sentenças diferentes
- Em grupo grande, pode haver múltiplos pares + processos distintos
- Se faltar .md, classifique INDEFINIDO + confianca BAIXA, não invente
"""


def gerar_fila(xlsx_path: Path, abas: list[str], forcar: bool):
    if not xlsx_path.exists():
        print(f"  ✗ Planilha não encontrada: {xlsx_path}")
        print(f"     Coloque o arquivo lá ou use --xlsx <caminho>")
        sys.exit(1)

    print(f"\n  Lendo: {xlsx_path}")
    print(f"  Abas: {', '.join(abas)}")

    grupos = ler_xlsx(xlsx_path, abas)
    if not grupos:
        print(f"  ✗ Nenhum grupo extraído das abas pedidas.")
        sys.exit(1)

    print(f"\n  Grupos encontrados: {len(grupos)}")

    # Filtrar já analisados
    controle = carregar_controle()
    ja_analisados = set(controle.get("grupos", {}).keys())

    if forcar:
        print(f"  --forcar: ignorando controle_grupos.json ({len(ja_analisados)} grupos)")
    else:
        antes = len(grupos)
        grupos = [g for g in grupos if g["group_id"] not in ja_analisados]
        if antes != len(grupos):
            print(f"  Já analisados (pulados): {antes - len(grupos)}")

    if not grupos:
        print(f"\n  Nada a fazer. Use --forcar para reprocessar tudo.")
        return

    # Estatística de distribuição
    pequenos = sum(1 for g in grupos if g["n_processos"] <= 3)
    medios = sum(1 for g in grupos if 4 <= g["n_processos"] <= 5)
    grandes = sum(1 for g in grupos if g["n_processos"] >= 6)
    print(f"\n  Distribuição:")
    print(f"    Pequenos (2-3 procs):  {pequenos}")
    print(f"    Médios   (4-5 procs):  {medios}")
    print(f"    Grandes  (6+ procs):   {grandes}")

    # Empacotar adaptativo
    cmds_pacotes = empacotar_adaptativo(grupos)

    print(f"\n  CMDs gerados: {len(cmds_pacotes)} (vs {len(grupos)} se fosse 1:1)")

    # Gerar comandos
    cmds_meta = []
    with open(CMDS_PATH, "w", encoding="utf-8") as f:
        f.write(f"# litispendencia — {len(cmds_pacotes)} comandos — "
                f"{datetime.now():%d/%m/%Y %H:%M}\n")
        f.write(f"# Total: {len(grupos)} grupos, "
                f"{sum(g['n_processos'] for g in grupos)} processos\n\n")

        for i, pacote in enumerate(cmds_pacotes, 1):
            texto = gerar_texto_cmd(i, pacote)
            f.write(texto + "\n\n")
            cmds_meta.append({
                "num": i,
                "grupos": [g["group_id"] for g in pacote],
                "processos": [c for g in pacote for c in g["processos"]],
                "n_grupos": len(pacote),
                "n_procs": sum(g["n_processos"] for g in pacote),
                "tipo": "LITISPENDENCIA",
            })

    # fila.json no formato compatível com FilaBase/auto_analisar
    fila = {
        "gerado_em": agora_iso(),
        "service": "litispendencia",
        "abas": abas,
        "total_grupos": len(grupos),
        "total_processos": sum(g["n_processos"] for g in grupos),
        "total_comandos": len(cmds_pacotes),
        "grupos_detalhe": [
            {
                "group_id": g["group_id"],
                "aba_origem": g["aba_origem"],
                "n_processos": g["n_processos"],
                "processos": g["processos"],
            }
            for g in grupos
        ],
        "comandos": cmds_meta,
    }
    FILA_PATH.write_text(
        json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n  ✓ Fila salva em:")
    print(f"    {FILA_PATH}")
    print(f"    {CMDS_PATH}")
    print(f"\n  Para executar: python auto_analisar_litispendencia.py")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--xlsx", default=str(DIR_FILES / "litispendencia.xlsx"),
                   help="Planilha de entrada (default: files/litispendencia.xlsx)")
    p.add_argument("--abas", default=",".join(ABAS_DEFAULT),
                   help="Abas a processar, separadas por vírgula")
    p.add_argument("--forcar", action="store_true",
                   help="Reprocessa mesmo grupos já em controle_grupos.json")
    args = p.parse_args()

    abas = [a.strip() for a in args.abas.split(",") if a.strip()]
    gerar_fila(Path(args.xlsx), abas, args.forcar)


if __name__ == "__main__":
    main()
