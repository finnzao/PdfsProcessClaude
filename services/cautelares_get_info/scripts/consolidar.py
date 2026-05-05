"""
services/cautelares_get_info/scripts/consolidar.py — Planilha alinhada ao CadastroInicialDTO.

Modelo: uma linha por processo (cadastro inicial é uma operação unificada
custodiado+endereço+processo+1º comparecimento). Se a mesma pessoa tem N
processos, são N linhas — o sistema duplica os dados pessoais por design.

Colunas seguem 1:1 a DTO. Duas colunas auxiliares (STATUS_CADASTRO e
MOTIVO_REVISAO) NÃO fazem parte da DTO — servem para o cartório triar e o
importador filtrar antes de mapear.

Validação local replica isDocumentoValido(): CPF ou RG é obrigatório.
"""

import json
import re
from datetime import datetime, date
from pathlib import Path
from typing import Optional


# ── Status operacional (coluna auxiliar) ────────────────────────

STATUS_PRONTO = "PRONTO"
STATUS_REVISAR = "REVISAR"
STATUS_BLOQUEADO = "BLOQUEADO"

# Status da cautelar que justificam cadastro
STATUS_CAU_CADASTRAVEIS = {"ATIVA"}
STATUS_CAU_REVISAVEIS = {"SUSPEITA_ATIVA", "AMBIGUA", "INDEFINIDO", "NUNCA_IMPOSTA"}
STATUS_CAU_NAO_CADASTRAR = {
    "EXTINTA_REVOGACAO", "EXTINTA_CUMPRIMENTO",
    "EXTINTA_ABSOLVICAO", "EXTINTA_PUNIBILIDADE",
    "CONVERTIDA_PREVENTIVA",
}

# Mapa de periodicidade → dias (integer da DTO)
PERIODICIDADE_DIAS = {
    "mensal": 30,
    "bimestral": 60,
    "quinzenal": 15,
    "semanal": 7,
    "trimestral": 90,
    "semestral": 180,
}


# ── Definição da planilha (espelha a DTO) ───────────────────────

# Cada entrada: (nome_coluna, largura, grupo_visual)
COLUNAS_DTO = [
    # Auxiliares operacionais (NÃO fazem parte da DTO)
    ("STATUS_CADASTRO",          12, "OP"),
    ("MOTIVO_REVISAO",           42, "OP"),

    # 1.1 Dados Pessoais
    ("nome",                     32, "PESSOAL"),
    ("contato",                  16, "PESSOAL"),

    # 1.2 Documentos
    ("cpf",                      16, "DOC"),
    ("rg",                       16, "DOC"),

    # 1.3 Dados Processuais
    ("processo",                 26, "PROC"),
    ("vara",                     26, "PROC"),
    ("comarca",                  16, "PROC"),
    ("dataDecisao",              12, "PROC"),
    ("dataComparecimentoInicial",14, "PROC"),

    # 1.4 Periodicidade
    ("periodicidade",            10, "PROC"),

    # 1.5 Endereço
    ("cep",                      11, "ENDR"),
    ("logradouro",               30, "ENDR"),
    ("numero",                   8,  "ENDR"),
    ("complemento",              16, "ENDR"),
    ("bairro",                   18, "ENDR"),
    ("cidade",                   16, "ENDR"),
    ("estado",                   6,  "ENDR"),

    # 1.6 Observações
    ("observacoes",              48, "OP"),
]

# Cores por grupo visual no cabeçalho
CORES_GRUPO = {
    "OP":      "595959",  # cinza escuro
    "PESSOAL": "1F3864",  # azul escuro
    "DOC":     "2E75B6",  # azul médio
    "PROC":    "548235",  # verde
    "ENDR":    "C55A11",  # laranja
}


# ── Normalizadores conforme regras da DTO ───────────────────────

def _norm_nome(s: str) -> str:
    """nome: 2-150 caracteres, sem espaços extras."""
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    return s[:150]


def _norm_contato(s: str) -> str:
    """contato: apenas números e ( ) . - espaço. Vazio vira 'Pendente'."""
    if not s:
        return "Pendente"
    permitidos = re.sub(r"[^\d() .\-]", "", s).strip()
    return permitidos if permitidos else "Pendente"


def _norm_cpf(s: str) -> str:
    """cpf: 000.000.000-00 ou 11 dígitos. Inválido vira ''."""
    if not s:
        return ""
    digitos = re.sub(r"\D", "", s)
    if len(digitos) != 11:
        return ""
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def _norm_rg(s: str) -> str:
    """rg: máximo 20 caracteres. Mantém formatação se existir."""
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    return s[:20]


def _norm_processo(s: str) -> str:
    """processo: apenas números, pontos e hífens."""
    if not s:
        return ""
    return re.sub(r"[^\d.\-]", "", s)


def _norm_texto(s: str, max_len: int) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()[:max_len]


def _norm_data(s: str) -> str:
    """Para yyyy-MM-dd. Aceita dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd."""
    if not s:
        return ""
    s = s.strip()
    # Já em ISO?
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$", s)
    if not m:
        return ""
    d, mo, a = m.groups()
    if len(a) == 2:
        a = ("20" + a) if int(a) < 50 else ("19" + a)
    try:
        return f"{int(a):04d}-{int(mo):02d}-{int(d):02d}"
    except ValueError:
        return ""


def _norm_cep(s: str) -> str:
    """cep: 00000-000 ou 8 dígitos."""
    if not s:
        return ""
    digitos = re.sub(r"\D", "", s)
    if len(digitos) != 8:
        return ""
    return f"{digitos[:5]}-{digitos[5:]}"


def _norm_estado(s: str) -> str:
    """estado: 2 letras maiúsculas."""
    if not s:
        return ""
    s = re.sub(r"[^A-Za-z]", "", s).upper()
    return s[:2] if len(s) >= 2 else ""


def _norm_periodicidade(periodicidade_str: str) -> Optional[int]:
    """
    Converte string de periodicidade para integer em dias (1-365).
    'mensal' -> 30, 'bimestral' -> 60, 'a cada 45 dias' -> 45.
    Retorna None se não conseguir extrair valor válido.
    """
    if not periodicidade_str:
        return None
    s = periodicidade_str.lower().strip()

    for nome, dias in PERIODICIDADE_DIAS.items():
        if nome in s:
            return dias

    # "a cada N dias/meses/semanas"
    m = re.search(r"a\s+cada\s+(\d+)\s+(dias?|meses|semanas)", s)
    if m:
        n = int(m.group(1))
        unidade = m.group(2)
        if "dia" in unidade:
            valor = n
        elif "mes" in unidade or "mês" in unidade:
            valor = n * 30
        elif "semana" in unidade:
            valor = n * 7
        else:
            return None
        return valor if 1 <= valor <= 365 else None

    return None


# ── Inferência de comparecimento inicial ────────────────────────

def _calcular_comparecimento_inicial(data_decisao_iso: str, periodicidade_dias: Optional[int]) -> str:
    """
    Heurística: data inicial = data da decisão + periodicidade.
    Se data ou periodicidade ausentes, retorna ''.
    LLM/humano pode sobrescrever se houver data explícita no termo.
    """
    if not data_decisao_iso or not periodicidade_dias:
        return ""
    try:
        dt = datetime.strptime(data_decisao_iso, "%Y-%m-%d").date()
        from datetime import timedelta
        return (dt + timedelta(days=periodicidade_dias)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return ""


# ── Construção da linha conforme DTO ────────────────────────────

def _get(d: dict, path: str, default=""):
    cur = d
    for p in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur


def _construir_linha(reg: dict, papel: dict) -> dict:
    """Constrói uma linha alinhada à DTO a partir do JSON pré-extraído."""
    qualif = reg.get("qualificacao", {})
    cau = reg.get("cautelar", {})
    meta = reg.get("metadados_processo", {})

    # Nome: prefere o do papel quando há divergência (papel é fonte oficial)
    nome_pje = _get(qualif, "nome")
    nome_papel = papel.get("nome_papel", "") if papel else ""
    nome_final = nome_papel or nome_pje

    # Datas
    data_decisao = _norm_data(_get(cau, "data_imposicao"))
    periodicidade_dias = _norm_periodicidade(_get(cau, "periodicidade"))
    data_comp_inicial = _calcular_comparecimento_inicial(data_decisao, periodicidade_dias)

    # Endereço — só preenche logradouro completo se tiver via no início
    logradouro_raw = _get(qualif, "logradouro")
    if logradouro_raw and not re.match(r"^(rua|av|avenida|tv|travessa|estrada|rod|rodovia|pra[çc]a)", logradouro_raw, re.I):
        logradouro_raw = "Rua " + logradouro_raw

    # Observações: monta texto operacional com peça-fonte e contexto
    observacoes_partes = []
    peca = _get(cau, "peca_fonte")
    pagina = _get(cau, "pagina_fonte")
    if peca:
        if pagina:
            observacoes_partes.append(f"Cadastro originado de {peca} ({pagina}).")
        else:
            observacoes_partes.append(f"Cadastro originado de {peca}.")
    livro = papel.get("livro", "") if papel else ""
    if livro:
        observacoes_partes.append(f"Livro físico: {livro}.")
    cond = _get(cau, "condicoes")
    if isinstance(cond, list) and cond:
        observacoes_partes.append("Condições adicionais: " + "; ".join(cond) + ".")
    observacoes = " ".join(observacoes_partes)

    linha = {
        # 1.1
        "nome": _norm_nome(nome_final),
        "contato": _norm_contato(_get(qualif, "telefone")),
        # 1.2
        "cpf": _norm_cpf(_get(qualif, "cpf")),
        "rg": _norm_rg(_get(qualif, "rg")),
        # 1.3
        "processo": _norm_processo(reg.get("numero_processo", "")),
        "vara": _norm_texto(_get(meta, "orgao_julgador") or "Vara Criminal de Rio Real", 100),
        "comarca": "Rio Real",
        "dataDecisao": data_decisao,
        "dataComparecimentoInicial": data_comp_inicial,
        # 1.4
        "periodicidade": periodicidade_dias if periodicidade_dias else "",
        # 1.5
        "cep": _norm_cep(_get(qualif, "cep")),
        "logradouro": _norm_texto(logradouro_raw, 200),
        "numero": _norm_texto(_get(qualif, "numero_endereco"), 20),
        "complemento": _norm_texto(_get(qualif, "complemento"), 100),
        "bairro": _norm_texto(_get(qualif, "bairro"), 100),
        "cidade": _norm_texto(_get(qualif, "cidade") or "Rio Real", 100),
        "estado": _norm_estado(_get(qualif, "estado") or "BA"),
        # 1.6
        "observacoes": observacoes,
    }
    return linha


# ── Validação conforme regras da DTO ────────────────────────────

def _validar_dto(linha: dict, status_cautelar: str) -> tuple[str, list[str]]:
    """
    Replica as validações da DTO.
    Retorna (STATUS_CADASTRO, lista_de_motivos).
    """
    motivos = []

    # Bloqueio por status de cautelar incompatível
    if status_cautelar in STATUS_CAU_NAO_CADASTRAR:
        motivos.append(f"cautelar {status_cautelar} — não cadastrar")
        return STATUS_BLOQUEADO, motivos

    # Validações duras (DTO @NotBlank/@AssertTrue)
    if not linha["nome"] or len(linha["nome"]) < 2:
        motivos.append("nome ausente ou muito curto")
    if len(linha["nome"]) > 150:
        motivos.append("nome excede 150 caracteres")

    # isDocumentoValido(): CPF OU RG obrigatório
    if not linha["cpf"] and not linha["rg"]:
        motivos.append("sem CPF nem RG (isDocumentoValido falha)")

    if not linha["processo"]:
        motivos.append("processo ausente")
    if not linha["vara"]:
        motivos.append("vara ausente")
    if not linha["comarca"]:
        motivos.append("comarca ausente")
    if not linha["dataDecisao"]:
        motivos.append("dataDecisao ausente")

    if not linha["periodicidade"] or not isinstance(linha["periodicidade"], int):
        motivos.append("periodicidade ausente")
    elif not (1 <= linha["periodicidade"] <= 365):
        motivos.append(f"periodicidade fora do intervalo 1-365: {linha['periodicidade']}")

    if not linha["cep"]:
        motivos.append("cep ausente")
    if not linha["logradouro"] or len(linha["logradouro"]) < 5:
        motivos.append("logradouro ausente ou < 5 caracteres")
    if not linha["bairro"] or len(linha["bairro"]) < 2:
        motivos.append("bairro ausente")
    if not linha["cidade"] or len(linha["cidade"]) < 2:
        motivos.append("cidade ausente")
    if not linha["estado"] or not re.match(r"^[A-Z]{2}$", linha["estado"]):
        motivos.append("estado inválido (sigla 2 letras)")

    # Erros bloqueantes (DTO rejeita)
    erros_bloqueantes = [
        "sem CPF nem RG",
        "nome ausente",
        "processo ausente",
        "vara ausente",
        "comarca ausente",
        "dataDecisao ausente",
        "periodicidade ausente",
        "cep ausente",
        "logradouro ausente",
        "bairro ausente",
        "cidade ausente",
        "estado inválido",
    ]
    if any(any(eb in m for eb in erros_bloqueantes) for m in motivos):
        return STATUS_BLOQUEADO, motivos

    # Avisos para revisão (passa na DTO mas merece olhar humano)
    if status_cautelar in STATUS_CAU_REVISAVEIS:
        motivos.append(f"cautelar {status_cautelar} — verificar antes de cadastrar")
    if linha["contato"] == "Pendente":
        motivos.append("telefone não localizado")
    if not linha["cpf"]:
        motivos.append("sem CPF (usando apenas RG)")
    if not linha["dataComparecimentoInicial"]:
        motivos.append("data inicial calculada não disponível")

    if motivos:
        return STATUS_REVISAR, motivos
    return STATUS_PRONTO, []


# ── Carregamento da lista do papel ──────────────────────────────

def _carregar_lista_papel(xlsx_path: Optional[Path]) -> dict[str, dict]:
    if not xlsx_path or not xlsx_path.exists():
        return {}
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("  AVISO: openpyxl não instalado, lista do papel ignorada")
        return {}
    wb = load_workbook(xlsx_path, read_only=True)
    ws = wb.active
    re_cnj = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d{1}\.\d{2}\.\d{4}")
    out = {}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0 or not row or not row[2]:
            continue
        num, processo, nome, livro, etiq = (row + (None,) * 5)[:5]
        m = re_cnj.search(str(processo or ""))
        if not m:
            continue
        out[m.group(0)] = {
            "num_papel": num,
            "nome_papel": str(nome or "").strip(),
            "livro": str(livro or "").strip(),
            "etiquetado": str(etiq or "").strip(),
        }
    wb.close()
    return out


# ── Pipeline principal ──────────────────────────────────────────

def consolidar(json_dir: Path, lista_papel: Optional[Path], saida_xlsx: Path):
    """
    Lê JSONs do pré-extrator, gera planilha xlsx única alinhada à DTO.
    """
    json_dir = Path(json_dir)
    saida_xlsx = Path(saida_xlsx)
    papel_idx = _carregar_lista_papel(Path(lista_papel) if lista_papel else None)

    linhas: list[dict] = []
    arquivos = sorted(json_dir.glob("*.json"))
    print(f"\n  Consolidando {len(arquivos)} processos...")

    for jp in arquivos:
        try:
            reg = json.loads(jp.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  AVISO {jp.name}: {e}")
            continue

        cnj = reg.get("numero_processo", "")
        papel = papel_idx.get(cnj, {})
        linha = _construir_linha(reg, papel)

        status_cautelar = _get(reg, "cautelar.status")
        status, motivos = _validar_dto(linha, status_cautelar)
        linha["STATUS_CADASTRO"] = status
        linha["MOTIVO_REVISAO"] = "; ".join(motivos)

        linhas.append(linha)

    _gerar_xlsx(linhas, saida_xlsx)
    _imprimir_resumo(linhas, saida_xlsx)


def _gerar_xlsx(linhas: list[dict], saida: Path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Cadastro"

    # Estilos
    cab_font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
    cab_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_font = Font(name="Arial", size=9)
    cell_align = Alignment(vertical="top", wrap_text=True)
    borda = Border(*[Side(style="thin", color="D9D9D9")] * 4)

    cores_status = {
        STATUS_PRONTO:    PatternFill("solid", fgColor="D9EAD3"),
        STATUS_REVISAR:   PatternFill("solid", fgColor="FFF2CC"),
        STATUS_BLOQUEADO: PatternFill("solid", fgColor="F4CCCC"),
    }
    fontes_status = {
        STATUS_PRONTO:    Font(name="Arial", size=9, bold=True, color="274E13"),
        STATUS_REVISAR:   Font(name="Arial", size=9, bold=True, color="7F6000"),
        STATUS_BLOQUEADO: Font(name="Arial", size=9, bold=True, color="990000"),
    }

    # Cabeçalho
    for col_idx, (nome_col, largura, grupo) in enumerate(COLUNAS_DTO, 1):
        c = ws.cell(row=1, column=col_idx, value=nome_col)
        c.font = cab_font
        c.fill = PatternFill("solid", fgColor=CORES_GRUPO[grupo])
        c.alignment = cab_align
        c.border = borda
        ws.column_dimensions[get_column_letter(col_idx)].width = largura
    ws.row_dimensions[1].height = 28
    ws.freeze_panes = "C2"

    if linhas:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUNAS_DTO))}{len(linhas) + 1}"

    # Dropdown de validação para STATUS_CADASTRO
    dv_status = DataValidation(
        type="list",
        formula1=f'"{STATUS_PRONTO},{STATUS_REVISAR},{STATUS_BLOQUEADO}"',
        allow_blank=False,
    )
    ws.add_data_validation(dv_status)

    # Dropdown para estado (UFs brasileiras)
    UFS = "AC,AL,AP,AM,BA,CE,DF,ES,GO,MA,MT,MS,MG,PA,PB,PR,PE,PI,RJ,RN,RS,RO,RR,SC,SP,SE,TO"
    dv_uf = DataValidation(type="list", formula1=f'"{UFS}"', allow_blank=False)
    ws.add_data_validation(dv_uf)

    # Linhas
    nomes_colunas = [c[0] for c in COLUNAS_DTO]
    col_status = nomes_colunas.index("STATUS_CADASTRO") + 1
    col_estado = nomes_colunas.index("estado") + 1
    col_periodicidade = nomes_colunas.index("periodicidade") + 1

    for row_idx, linha in enumerate(linhas, 2):
        for col_idx, nome_col in enumerate(nomes_colunas, 1):
            v = linha.get(nome_col, "")
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            # openpyxl converte "" para None ao salvar. Para garantir que o
            # importador veja célula vazia (e não None que pode quebrar parse),
            # passamos None explicitamente — vai gerar célula vazia, não null.
            if v == "" or v is None:
                v = None
            c = ws.cell(row=row_idx, column=col_idx, value=v)
            c.font = cell_font
            c.alignment = cell_align
            c.border = borda

        # Tipa periodicidade como número se possível
        per_val = linha.get("periodicidade")
        if isinstance(per_val, int):
            ws.cell(row=row_idx, column=col_periodicidade).number_format = "0"

        # Realça STATUS_CADASTRO
        status = linha.get("STATUS_CADASTRO", "")
        if status in cores_status:
            ws.cell(row=row_idx, column=col_status).fill = cores_status[status]
            ws.cell(row=row_idx, column=col_status).font = fontes_status[status]

        # Aplica dropdowns
        dv_status.add(ws.cell(row=row_idx, column=col_status).coordinate)
        dv_uf.add(ws.cell(row=row_idx, column=col_estado).coordinate)

    saida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(saida)


def _imprimir_resumo(linhas: list[dict], saida: Path):
    n = len(linhas)
    n_pronto = sum(1 for l in linhas if l["STATUS_CADASTRO"] == STATUS_PRONTO)
    n_revisar = sum(1 for l in linhas if l["STATUS_CADASTRO"] == STATUS_REVISAR)
    n_bloq = sum(1 for l in linhas if l["STATUS_CADASTRO"] == STATUS_BLOQUEADO)

    print(f"\n  ── Resumo da consolidação ──")
    print(f"  Total de linhas:  {n}")
    print(f"  PRONTO:           {n_pronto:>3}  (importador consome)")
    print(f"  REVISAR:          {n_revisar:>3}  (humano analisa)")
    print(f"  BLOQUEADO:        {n_bloq:>3}  (descartado)")
    print(f"\n  Planilha: {saida}")


if __name__ == "__main__":
    import sys
    json_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "pre_extraido")
    papel = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    saida = Path(sys.argv[3] if len(sys.argv) > 3 else "result/cadastro_inicial.xlsx")
    consolidar(json_dir, papel, saida)
