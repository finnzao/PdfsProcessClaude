#!/usr/bin/env python3
"""
main.py — Missão 2: Extração de dados de custodiados para cadastro ACLP.

O Claude Code lê cada processo e extrai:
- Dados pessoais (nome, CPF, RG, endereço, telefone)
- Dados processuais (processo, vara, comarca)
- Decisão: se o réu PRECISA ou NÃO comparecer (e o motivo)

Saída final: planilha .xlsx pronta para cadastro no sistema.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from common.fila_base import FilaBase
from common.consolidar_base import ConsolidarBase
from common.checkpoint import CheckpointManager
from common.sessao import SessaoManager
from common.utils import DIR_RESULT


SERVICE_DIR = Path(__file__).parent
RESULT_DIR = DIR_RESULT / "cautelares_get_info"


# ============================================================
# FILA DE EXTRAÇÃO DE CUSTODIADOS
# ============================================================
class FilaCustodiados(FilaBase):
    SERVICE_NAME = "cautelares_get_info"
    BATCH_COM_PDF = 3
    BATCH_SEM_PDF = 10

    # Todas as classes usam o mesmo prompt de extração de custodiados
    CLASSE_PARA_PROMPT = {}

    def _prompt_default(self):
        return "prompt_custodiado.md"

    def _prompt_para_classe(self, classe):
        return "prompt_custodiado.md"

    def gerar_comando_com_pdf(self, cmd_num, processos, prompt_file):
        arquivos = "\n".join(
            f"  - textos_extraidos/{p['txt_arquivo']}"
            f"  ({p['numero']} | {p['classe']} | {p['assunto']})"
            for p in processos
        )
        nums = " ".join(p["numero"] for p in processos)
        sp = "services/cautelares_get_info"

        return f"""# === COMANDO {cmd_num:03d} === [CUSTODIADO] [{len(processos)} com PDF] ===
# Processos: {nums}
# Ao concluir: python run.py cautelares marcar {cmd_num} {nums}

Leia o prompt em {sp}/prompts/{prompt_file}.
Para CADA processo, leia o .txt completo e extraia os dados do réu/custodiado:

{arquivos}

Salve em {sp}/resultados/custodiado_{cmd_num:03d}.json"""

    def gerar_comando_sem_pdf(self, cmd_num, processos, prompt_file):
        tabela = "| Número | Classe | Assunto | Última Mov. |\n"
        tabela += "|--------|--------|---------|------------|\n"
        for p in processos:
            tabela += f"| {p['numero']} | {p['classe']} | {p['assunto']} | {p['ultima_mov'][:50]} |\n"
        nums = " ".join(p["numero"] for p in processos)
        sp = "services/cautelares_get_info"

        return f"""# === COMANDO {cmd_num:03d} === [CUSTODIADO] [{len(processos)} SEM PDF] ===
# Processos: {nums}
# Ao concluir: python run.py cautelares marcar {cmd_num} {nums}

Leia {sp}/prompts/{prompt_file}.
Extraia APENAS os dados disponíveis no CSV (análise limitada):

{tabela}

Salve em {sp}/resultados/custodiado_{cmd_num:03d}.json"""


# ============================================================
# CONSOLIDAÇÃO → XLSX
# ============================================================
class ConsolidarCustodiados(ConsolidarBase):
    SERVICE_NAME = "cautelares_get_info"

    def consolidar(self):
        print("=" * 60)
        print("  CONSOLIDAÇÃO — Custodiados → XLSX")
        print("=" * 60)

        jsons = sorted(self.resultados_dir.glob("custodiado_*.json"))
        if not jsons:
            print(f"  ❌ Nenhum resultado em {self.resultados_dir}/")
            return

        print(f"  {len(jsons)} arquivos encontrados")

        todos = []
        for jp in jsons:
            try:
                with open(jp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    todos.extend(data)
                elif isinstance(data, dict):
                    if "custodiados" in data:
                        todos.extend(data["custodiados"])
                    else:
                        todos.append(data)
            except Exception as e:
                print(f"  ⚠️  Erro: {jp.name}: {e}")

        if not todos:
            print("  ❌ Nenhum custodiado encontrado.")
            return

        print(f"  {len(todos)} custodiados extraídos")

        saida = self.result_dir / "custodiados_para_cadastro.xlsx"
        self._gerar_xlsx(todos, saida)
        print(f"\n  ✅ Planilha: {saida}")

    def _gerar_xlsx(self, custodiados, saida_path):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            print("  ❌ openpyxl não instalado. Rode: pip install openpyxl")
            return

        wb = Workbook()
        ws = wb.active
        ws.title = "Cadastro Custodiados"

        hf = Font(name='Arial', bold=True, color='FFFFFF', size=11)
        hfill = PatternFill('solid', fgColor='2F5496')
        halign = Alignment(horizontal='center', vertical='center', wrap_text=True)
        amarelo = PatternFill('solid', fgColor='FFF2CC')
        vermelho = PatternFill('solid', fgColor='F4CCCC')
        verde = PatternFill('solid', fgColor='D9EAD3')
        nf = Font(name='Arial', size=10)
        borda = Border(
            left=Side(style='thin', color='D9D9D9'),
            right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'),
            bottom=Side(style='thin', color='D9D9D9'),
        )

        headers = [
            ('A', 'Nome', 25), ('B', 'CPF', 16), ('C', 'RG', 16),
            ('D', 'Contato', 18), ('E', 'Processo', 28),
            ('F', 'Vara', 25), ('G', 'Comarca', 15),
            ('H', 'Data Decisão', 14), ('I', 'Periodicidade (dias)', 14),
            ('J', 'Data Compar. Inicial', 16),
            ('K', 'CEP', 12), ('L', 'Logradouro', 30), ('M', 'Número', 10),
            ('N', 'Complemento', 15), ('O', 'Bairro', 20),
            ('P', 'Cidade', 15), ('Q', 'Estado', 8),
            ('R', 'Precisa Comparecer', 16),
            ('S', 'Motivo', 35),
            ('T', 'Observações', 40),
            ('U', 'Status Doc', 18),
        ]
        for col, title, width in headers:
            cell = ws[f'{col}1']
            cell.value = title
            cell.font = hf
            cell.fill = hfill
            cell.alignment = halign
            cell.border = borda
            ws.column_dimensions[col].width = width

        ws.row_dimensions[1].height = 35
        ws.auto_filter.ref = f"A1:U{len(custodiados) + 1}"
        ws.freeze_panes = 'A2'

        PREENCHER = "PREENCHER MANUALMENTE"

        for i, c in enumerate(custodiados, 2):
            cpf = c.get('cpf', '')
            rg = c.get('rg', '')
            has_doc = bool(cpf) or bool(rg)

            row = [
                c.get('nome', PREENCHER),
                cpf, rg,
                c.get('contato', PREENCHER),
                c.get('processo', ''),
                c.get('vara', 'Vara Criminal de Rio Real'),
                c.get('comarca', 'Rio Real'),
                c.get('dataDecisao', PREENCHER),
                c.get('periodicidade', PREENCHER),
                c.get('dataComparecimentoInicial', PREENCHER),
                c.get('cep', PREENCHER),
                c.get('logradouro', PREENCHER),
                c.get('numero_endereco', ''),
                c.get('complemento', ''),
                c.get('bairro', PREENCHER),
                c.get('cidade', 'Rio Real'),
                c.get('estado', 'BA'),
                c.get('precisa_comparecer', 'VERIFICAR'),
                c.get('motivo_comparecimento', ''),
                c.get('observacoes', ''),
                'OK' if has_doc else 'SEM DOCUMENTO',
            ]

            for j, val in enumerate(row):
                cell = ws.cell(row=i, column=j + 1, value=val)
                cell.font = nf
                cell.border = borda
                if val == PREENCHER:
                    cell.fill = amarelo
                elif val == 'SEM DOCUMENTO':
                    cell.fill = vermelho
                elif val == 'OK':
                    cell.fill = verde

        saida_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(saida_path)


# ============================================================
# INTERFACE
# ============================================================
def executar(comando, args=None):
    args = args or []

    if comando == "fila":
        print("=" * 60)
        print("  GERAR FILA — Custodiados")
        print("=" * 60)
        fila = FilaCustodiados(SERVICE_DIR)
        fila.gerar()

    elif comando == "status":
        print("=" * 60)
        print("  STATUS — Custodiados")
        print("=" * 60)
        fila = FilaCustodiados(SERVICE_DIR)
        fila.status()

    elif comando == "analisar":
        sm = SessaoManager(SERVICE_DIR / "checkpoint.json")
        sm.inicio()
        print("  Abra comandos_claude_code.txt e cole os comandos no Claude Code.")
        print(f"  Arquivo: {SERVICE_DIR / 'comandos_claude_code.txt'}")

    elif comando == "pausa":
        sm = SessaoManager(SERVICE_DIR / "checkpoint.json")
        sm.fim(SERVICE_DIR / "fila.json")

    elif comando == "marcar":
        if len(args) < 1:
            print("  USO: python run.py cautelares marcar <NUM> [PROCESSOS...]")
            return
        cm = CheckpointManager(SERVICE_DIR / "checkpoint.json")
        cmd_num = int(args[0])
        processos = args[1:]
        cm.marcar_concluido(cmd_num, processos,
                            f"resultados/custodiado_{cmd_num:03d}.json")

    elif comando == "consolidar":
        c = ConsolidarCustodiados(SERVICE_DIR, RESULT_DIR)
        c.consolidar()

    elif comando == "reset":
        cm = CheckpointManager(SERVICE_DIR / "checkpoint.json")
        cm.reset()
        for f in [SERVICE_DIR / "fila.json", SERVICE_DIR / "comandos_claude_code.txt"]:
            if f.exists():
                f.unlink()
        print("  Reset completo.")

    else:
        print(f"  Comando desconhecido: {comando}")
        print("  Disponíveis: fila, status, analisar, pausa, marcar, consolidar, reset")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("USO: python -m services.cautelares_get_info.main <comando>")
        sys.exit(1)
    executar(sys.argv[1], sys.argv[2:])
