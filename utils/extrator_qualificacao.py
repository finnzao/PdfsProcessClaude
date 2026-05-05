"""
utils/extrator_qualificacao.py — Extração estruturada de dados do réu.

Lê o markdown extraído de um processo e captura:
    nome, CPF, RG, filiação (mãe/pai), data de nascimento, naturalidade,
    estado civil, profissão, escolaridade, endereço, telefone

A estratégia explora a estrutura conhecida das peças de qualificação:
    - Boletim de Ocorrência (BO): traz blocos "Qualificação do(a) Indiciado(a)"
    - Denúncia: traz qualificação no preâmbulo, após "denuncia"
    - Interrogatório: traz qualificação no início
    - Audiência de custódia: traz qualificação na ata

CRÍTICO: o módulo distingue réu de vítima/testemunha pelos marcadores
contextuais. Capturar CPF da vítima como sendo do réu é o erro mais grave
que poderia ocorrer no pipeline.

Uso:
    from utils.extrator_qualificacao import extrair_qualificacao_reu

    md = Path("textos_extraidos/0001234_56_2024_8_05_0216.md").read_text()
    dados = extrair_qualificacao_reu(md)
    # dados["nome"], dados["cpf"], dados["confianca"]["cpf"], etc.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Optional, Tuple


# ── Regex de campos ──────────────────────────────────────────────

RE_CPF = re.compile(r"\b(\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b")
RE_RG = re.compile(
    r"(?:RG|R\.?\s*G\.?|identidade)[\s:.\-Nº°ºn]*"
    r"([\d.\-]{5,18}(?:\s*[/\-]?\s*[A-Z]{2,5})?)",
    re.I,
)
RE_TELEFONE = re.compile(
    r"\(?\b(?P<ddd>\d{2})\)?\s*(?P<meio>(?:9\s?\d{4})|(?:\d{4,5}))\s*[-.\s]?\s*(?P<fim>\d{4})\b"
)
RE_CEP = re.compile(r"\b(\d{5}-?\d{3})\b")
RE_DATA = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")

# Nome próprio em português: 2-7 palavras com maiúscula (incluindo "da", "de", etc.)
RE_NOME_PROPRIO = re.compile(
    r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÀÈÌÒÙÄËÏÖÜÇÑ][a-záéíóúâêôãõàèìòùäëïöüçñ]+"
    r"(?:\s+(?:d[aeo]s?|e|von|van|del|della)\s+|\s+)"
    r"[A-ZÁÉÍÓÚÂÊÔÃÕÀÈÌÒÙÄËÏÖÜÇÑ][a-záéíóúâêôãõàèìòùäëïöüçñ]+"
    r"(?:\s+(?:d[aeo]s?|e|von|van|del|della|[A-ZÁÉÍÓÚÂÊÔÃÕÀÈÌÒÙÄËÏÖÜÇÑ][a-záéíóúâêôãõàèìòùäëïöüçñ]+))*)"
)

RE_NOME_TODO_MAIUSCULO = re.compile(
    r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÀÈÌÒÙÄËÏÖÜÇÑ]{2,}"
    r"(?:\s+(?:D[AEO]S?|E|VON|VAN|DEL|DELLA|"
    r"[A-ZÁÉÍÓÚÂÊÔÃÕÀÈÌÒÙÄËÏÖÜÇÑ]{2,})){1,6})\b"
)


# ── Marcadores de papel processual ───────────────────────────────

# Quando a janela de busca contém um marcador desta lista, o que vier depois
# é provavelmente do réu (até encontrar marcador de outro papel).
MARCADORES_REU = [
    re.compile(r"\bR[ÉE]U(?:\(é\))?\s*:", re.I),
    re.compile(r"\bACUSAD[OA]\s*:", re.I),
    re.compile(r"\bINDICIAD[OA]\s*:", re.I),
    re.compile(r"\bDENUNCIAD[OA]\s*:", re.I),
    re.compile(r"\bINVESTIGAD[OA]\s*:", re.I),
    re.compile(r"\bAUTOR DO FATO\s*:", re.I),
    re.compile(r"\bQualifica[çc][aã]o do\(?a?\)?\s+(?:r[ée]u|acusad|indiciad|denunciad)", re.I),
    re.compile(r"\bDADOS DO\(A\)\s+(?:R[ÉE]U|ACUSAD|INDICIAD)", re.I),
    re.compile(r"\bIDENTIFICA[ÇC][AÃ]O DO\(A\)\s+(?:R[ÉE]U|ACUSAD)", re.I),
    re.compile(r"\bcustodiad[oa]\s*:", re.I),
    re.compile(r"\bconduzid[oa]\s*:", re.I),
]

MARCADORES_VITIMA = [
    re.compile(r"\bV[ÍI]TIMA\s*:", re.I),
    re.compile(r"\bOFENDID[OA]\s*:", re.I),
    re.compile(r"\bQualifica[çc][aã]o\s+da\s+v[íi]tima", re.I),
    re.compile(r"\bDADOS DA\s+V[ÍI]TIMA", re.I),
]

MARCADORES_TESTEMUNHA = [
    re.compile(r"\bTESTEMUNHA\s*:", re.I),
    re.compile(r"\bQualifica[çc][aã]o\s+da\s+testemunha", re.I),
]

MARCADORES_OUTROS = [
    re.compile(r"\bADVOGAD[OA]\s*:", re.I),
    re.compile(r"\bDEFENSOR[A]?\s*:", re.I),
    re.compile(r"\bPROMOTOR[A]?\s*:", re.I),
    re.compile(r"\bJU[ÍI]Z[A]?\s*:", re.I),
    re.compile(r"\bSERVENTU[ÁA]RI[OA]", re.I),
]


# ── Patterns de campo dentro de uma janela do réu ────────────────

CAMPOS_LABEL = {
    "nome": [
        re.compile(r"(?:nome|nome\s+completo)\s*:\s*([^\n;]+)", re.I),
    ],
    "cpf": [
        re.compile(r"CPF[\s:.\-Nº°ºn]+(\d{3}\.?\d{3}\.?\d{3}-?\d{2})", re.I),
    ],
    "rg": [
        re.compile(
            r"(?:RG|R\.?\s*G\.?|identidade|carteira\s+de\s+identidade)"
            r"[\s:.\-Nº°ºn]+([\d.\-]{5,18}(?:\s*[/\-]?\s*[A-Z]{2,5}/?[A-Z]{0,2})?)",
            re.I,
        ),
    ],
    "nome_mae": [
        # "Filiação: <Mãe> e <Pai>" → captura só até o " e "
        re.compile(r"(?:filia[çc][aã]o|m[ãa]e)\s*:\s*([^\n;]+?)(?:\s+e\s+[A-ZÁ-Ú]|\s*(?:e\s+)?pai[\s:]|\n|;|$)", re.I),
        re.compile(r"\bm[ãa]e\s*:\s*([^\n;]+)", re.I),
        re.compile(r"\bfilh[oa]\s+de\s+([A-ZÁ-Ú][^,\n]+?)(?:\s+(?:e|com)\s+[A-ZÁ-Ú])", re.I),
    ],
    "nome_pai": [
        re.compile(r"\bpai\s*:\s*([^\n;]+)", re.I),
        # "Filiação: Mãe e <Pai>" → captura tudo após o "e"
        re.compile(r"(?:filia[çc][aã]o|m[ãa]e)\s*:\s*[^\n;]+?\s+e\s+([A-ZÁ-Ú][^\n;]+)", re.I),
        re.compile(r"\bfilh[oa]\s+de\s+[^,\n]+?\s+(?:e|com)\s+([A-ZÁ-Ú][^,\n]+)", re.I),
    ],
    "data_nascimento": [
        re.compile(
            r"(?:nascid[oa]\s+(?:em|aos?)|data\s+de\s+nascimento|nasc\.?)"
            r"\s*:?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
            re.I,
        ),
        re.compile(
            r"\bnascid[oa]\s+(?:em|aos?)\s+(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
            re.I,
        ),
    ],
    "naturalidade": [
        re.compile(r"natural\s+(?:de|d[ao])\s*:?\s*([A-ZÁ-Ú][^,\n;]+?)(?:[,\-/]|\n)", re.I),
        re.compile(r"naturalidade\s*:\s*([^\n;]+)", re.I),
    ],
    "nacionalidade": [
        re.compile(r"nacionalidade\s*:\s*([^\n;]+)", re.I),
        re.compile(r"\b(brasileir[oa]|estrangeir[oa])\b", re.I),
    ],
    "estado_civil": [
        re.compile(
            r"\b(solteir[oa]|casad[oa]|divorciad[oa]|vi[úu]v[oa]|"
            r"separad[oa]|uni[ãa]o\s+est[áa]vel|amasiad[oa])\b",
            re.I,
        ),
    ],
    "profissao": [
        re.compile(r"profiss[ãa]o\s*:\s*([^\n;]+)", re.I),
        re.compile(r"ocupa[çc][aã]o\s*:\s*([^\n;]+)", re.I),
    ],
    "escolaridade": [
        re.compile(r"escolaridade\s*:\s*([^\n;]+)", re.I),
        re.compile(
            r"\b(analfabet[oa]|fundamental|m[ée]dio|superior|"
            r"alfabetizad[oa])(?:\s+(?:completo|incompleto|cursando))?",
            re.I,
        ),
    ],
    "telefone": [
        re.compile(r"(?:telefone|celular|tel\.?|cel\.?|fone)\s*:?\s*"
                   r"\(?(\d{2})\)?\s*(\d{4,5})[-.\s]?(\d{4})", re.I),
    ],
    "cep": [
        re.compile(r"CEP\s*:?\s*(\d{5}-?\d{3})", re.I),
    ],
    "endereco_completo": [
        re.compile(
            r"(?:endere[çc]o|residente|domiciliad[oa]\s+em)"
            r"\s*:?\s*([^\n]+(?:\n[^\n]+){0,2})",
            re.I,
        ),
    ],
    "logradouro": [
        re.compile(
            r"\b(?:rua|av\.?|avenida|tv\.?|travessa|estrada|rod\.?|rodovia|pra[çc]a)\s+"
            r"([^,\n]+?)(?:[,\n]|n[º°]|nº|\d)",
            re.I,
        ),
    ],
    "bairro": [
        re.compile(r"bairro\s*:?\s*([^,\n;]+)", re.I),
    ],
    "cidade": [
        re.compile(r"(?:cidade|munic[íi]pio)\s*:?\s*([^,\n;]+?)(?:[,/]|\bUF\b|\n|$)", re.I),
        # Padrão "Bairro X, Cidade/UF" muito comum em endereços de BO
        re.compile(r",\s*([A-ZÁ-Ú][a-záéíóúâêôãõç]+(?:\s+[A-ZÁ-Ú][a-záéíóúâêôãõç]+){0,3})\s*/\s*[A-Z]{2}\b", re.I),
    ],
}


# ── Modelo de saída ──────────────────────────────────────────────

@dataclass
class DadosReu:
    """Dados do réu com indicador de confiança por campo."""
    nome: str = ""
    cpf: str = ""
    rg: str = ""
    nome_mae: str = ""
    nome_pai: str = ""
    data_nascimento: str = ""
    naturalidade: str = ""
    nacionalidade: str = ""
    estado_civil: str = ""
    profissao: str = ""
    escolaridade: str = ""
    telefone: str = ""
    cep: str = ""
    logradouro: str = ""
    numero_endereco: str = ""
    complemento: str = ""
    bairro: str = ""
    cidade: str = ""
    estado: str = ""
    endereco_bruto: str = ""

    # Metadados de extração
    confianca: dict = field(default_factory=dict)  # campo -> "alta"|"media"|"baixa"
    fonte: dict = field(default_factory=dict)      # campo -> "BO"|"DENÚNCIA"|"AUDIÊNCIA"
    multiplos_reus: bool = False
    nomes_candidatos: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def campos_preenchidos(self) -> int:
        """Conta campos não-vazios (exclui metadados)."""
        skip = {"confianca", "fonte", "multiplos_reus", "nomes_candidatos", "endereco_bruto"}
        return sum(1 for k, v in asdict(self).items() if k not in skip and v)


# ── Helpers ──────────────────────────────────────────────────────

def _formatar_cpf(cpf: str) -> str:
    digitos = re.sub(r"\D", "", cpf)
    if len(digitos) != 11:
        return cpf.strip()
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def _formatar_telefone(ddd: str, meio: str, fim: str) -> str:
    meio_limpo = re.sub(r"\s+", "", meio)
    return f"({ddd}) {meio_limpo}-{fim}"


def _formatar_cep(cep: str) -> str:
    digitos = re.sub(r"\D", "", cep)
    if len(digitos) != 8:
        return cep.strip()
    return f"{digitos[:5]}-{digitos[5:]}"


def _limpar(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" ,;.\n\t")


def _extrair_secoes_pecas(md: str) -> list[dict]:
    """
    Recebe o markdown completo e retorna lista de seções com tipo identificado.
    Espera o formato gerado pelo extrair_processos.py:
        ## TIPO (p.X-Y) [Num. ZZZ]
        texto...
    """
    secoes = []
    pattern = re.compile(r"^##\s+([A-ZÁ-ÚÇ_ ]+)\s*\(", re.M)

    matches = list(pattern.finditer(md))
    for i, m in enumerate(matches):
        tipo = m.group(1).strip()
        inicio = m.end()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        texto = md[inicio:fim].strip()
        if texto:
            secoes.append({"tipo": tipo, "texto": texto})
    return secoes


def _achar_janela_reu(texto: str) -> Optional[Tuple[int, int]]:
    """
    Localiza a janela de texto que descreve o réu.
    Retorna (inicio, fim) ou None se nenhum marcador foi encontrado.

    Janela vai do marcador do réu até o próximo marcador de outro papel
    (vítima, testemunha, advogado) ou até 1500 chars depois.
    """
    inicio_reu = None
    for marcador in MARCADORES_REU:
        m = marcador.search(texto)
        if m and (inicio_reu is None or m.start() < inicio_reu):
            inicio_reu = m.start()

    if inicio_reu is None:
        return None

    # Encontra o próximo marcador de outro papel
    todos_outros = MARCADORES_VITIMA + MARCADORES_TESTEMUNHA + MARCADORES_OUTROS
    fim_reu = inicio_reu + 1500
    for marcador in todos_outros:
        for m in marcador.finditer(texto):
            if m.start() > inicio_reu and m.start() < fim_reu:
                fim_reu = m.start()

    return (inicio_reu, fim_reu)


def _extrair_da_janela(janela: str, dados: DadosReu, fonte_nome: str):
    """Aplica os patterns CAMPOS_LABEL na janela e preenche `dados`."""

    def setif(campo: str, valor: str, conf: str = "alta"):
        if not valor or getattr(dados, campo, ""):
            return
        setattr(dados, campo, _limpar(valor))
        dados.confianca[campo] = conf
        dados.fonte[campo] = fonte_nome

    # Nome (label explícito)
    for pat in CAMPOS_LABEL["nome"]:
        m = pat.search(janela)
        if m:
            nome = _limpar(m.group(1))
            # Filtra: deve ter pelo menos 2 palavras com inicial maiúscula
            if len(nome.split()) >= 2 and re.search(r"[A-ZÁ-Ú]", nome):
                setif("nome", nome, "alta")
                break

    # CPF
    for pat in CAMPOS_LABEL["cpf"]:
        m = pat.search(janela)
        if m:
            setif("cpf", _formatar_cpf(m.group(1)), "alta")
            break
    # CPF sem label (se ainda não achou): primeiro CPF na janela do réu
    if not dados.cpf:
        m = RE_CPF.search(janela)
        if m:
            setif("cpf", _formatar_cpf(m.group(1)), "media")

    # RG
    for pat in CAMPOS_LABEL["rg"]:
        m = pat.search(janela)
        if m:
            setif("rg", m.group(1), "alta")
            break

    # Filiação - mãe
    for pat in CAMPOS_LABEL["nome_mae"]:
        m = pat.search(janela)
        if m:
            setif("nome_mae", m.group(1), "alta")
            break

    # Filiação - pai
    for pat in CAMPOS_LABEL["nome_pai"]:
        m = pat.search(janela)
        if m:
            setif("nome_pai", m.group(1), "alta")
            break

    # Data de nascimento
    for pat in CAMPOS_LABEL["data_nascimento"]:
        m = pat.search(janela)
        if m:
            setif("data_nascimento", m.group(1), "alta")
            break

    # Naturalidade
    for pat in CAMPOS_LABEL["naturalidade"]:
        m = pat.search(janela)
        if m:
            setif("naturalidade", m.group(1), "alta")
            break

    # Nacionalidade
    for pat in CAMPOS_LABEL["nacionalidade"]:
        m = pat.search(janela)
        if m:
            setif("nacionalidade", m.group(1).capitalize(), "media")
            break

    # Estado civil
    for pat in CAMPOS_LABEL["estado_civil"]:
        m = pat.search(janela)
        if m:
            setif("estado_civil", m.group(1).capitalize(), "media")
            break

    # Profissão
    for pat in CAMPOS_LABEL["profissao"]:
        m = pat.search(janela)
        if m:
            setif("profissao", m.group(1), "alta")
            break

    # Escolaridade
    for pat in CAMPOS_LABEL["escolaridade"]:
        m = pat.search(janela)
        if m:
            setif("escolaridade", m.group(1), "media")
            break

    # Telefone
    for pat in CAMPOS_LABEL["telefone"]:
        m = pat.search(janela)
        if m:
            setif("telefone", _formatar_telefone(m.group(1), m.group(2), m.group(3)), "alta")
            break
    # Telefone sem label
    if not dados.telefone:
        m = RE_TELEFONE.search(janela)
        if m:
            ddd = m.group("ddd")
            if ddd not in ("19", "20"):  # falsos positivos comuns
                setif("telefone", _formatar_telefone(m.group("ddd"), m.group("meio"), m.group("fim")), "media")

    # CEP
    for pat in CAMPOS_LABEL["cep"]:
        m = pat.search(janela)
        if m:
            setif("cep", _formatar_cep(m.group(1)), "alta")
            break

    # Logradouro
    for pat in CAMPOS_LABEL["logradouro"]:
        m = pat.search(janela)
        if m:
            tipo_via = re.search(r"\b(rua|av\.?|avenida|tv\.?|travessa|estrada|rod\.?|rodovia|pra[çc]a)\b", m.group(0), re.I)
            prefixo = tipo_via.group(0).capitalize() if tipo_via else ""
            setif("logradouro", f"{prefixo} {m.group(1)}".strip(), "media")
            break

    # Bairro
    for pat in CAMPOS_LABEL["bairro"]:
        m = pat.search(janela)
        if m:
            setif("bairro", m.group(1), "alta")
            break

    # Cidade
    for pat in CAMPOS_LABEL["cidade"]:
        m = pat.search(janela)
        if m:
            setif("cidade", m.group(1), "alta")
            break

    # Endereço bruto (fallback para o LLM revisar)
    for pat in CAMPOS_LABEL["endereco_completo"]:
        m = pat.search(janela)
        if m and not dados.endereco_bruto:
            dados.endereco_bruto = _limpar(m.group(1))[:300]
            break


# ── Função principal ─────────────────────────────────────────────

# Ordem de prioridade das peças para extração de dados pessoais.
# BO geralmente é o mais completo, depois denúncia, audiência, interrogatório.
PRIORIDADE_PECAS = [
    "BO", "AUDIENCIA_CUSTODIA", "DENÚNCIA", "INTERROGATÓRIO",
    "DECLARAÇÃO", "TERMO_COMPROMISSO", "ATA", "DECISÃO",
]


def extrair_qualificacao_reu(md_completo: str) -> DadosReu:
    """
    Extrai dados de qualificação do réu a partir do markdown do processo.

    Estratégia:
      1. Quebra o markdown em seções por peça
      2. Para cada peça da PRIORIDADE_PECAS, localiza a janela do réu
         (entre marcador "Réu:" e próximo marcador de outro papel)
      3. Aplica patterns de campo na janela
      4. Preenche `dados` parcimoniosamente — só sobrescreve se confiança maior
    """
    dados = DadosReu(nacionalidade="Brasileira")  # default razoável
    secoes = _extrair_secoes_pecas(md_completo)

    if not secoes:
        # Fallback: trabalha com o texto inteiro
        secoes = [{"tipo": "DOC", "texto": md_completo}]

    # Detecta se há múltiplos réus (mais de um marcador de réu na denúncia)
    denuncia_texto = next((s["texto"] for s in secoes if s["tipo"] == "DENÚNCIA"), "")
    marcadores_reu_count = sum(
        len(m.findall(denuncia_texto)) for m in MARCADORES_REU
    )
    dados.multiplos_reus = marcadores_reu_count > 1

    # Processa peças em ordem de prioridade
    secoes_por_tipo = {s["tipo"]: s for s in secoes}
    for tipo_pri in PRIORIDADE_PECAS:
        if tipo_pri not in secoes_por_tipo:
            continue
        secao = secoes_por_tipo[tipo_pri]
        janela = _achar_janela_reu(secao["texto"])
        if janela is None:
            # Sem marcador explícito de réu — usa primeiros 1500 chars
            # (BO geralmente começa pela qualificação)
            janela = (0, min(1500, len(secao["texto"])))
        inicio, fim = janela
        _extrair_da_janela(secao["texto"][inicio:fim], dados, tipo_pri)

    # Coleta candidatos a nome (todos os nomes próprios em janelas de réu)
    if not dados.nome:
        candidatos = []
        for tipo_pri in PRIORIDADE_PECAS:
            if tipo_pri not in secoes_por_tipo:
                continue
            secao = secoes_por_tipo[tipo_pri]
            janela = _achar_janela_reu(secao["texto"]) or (0, 1500)
            inicio, fim = janela
            trecho = secao["texto"][inicio:fim]
            for m in RE_NOME_TODO_MAIUSCULO.finditer(trecho[:500]):
                candidatos.append(m.group(1))
            for m in RE_NOME_PROPRIO.finditer(trecho[:500]):
                candidatos.append(m.group(1))
        # Deduplica preservando ordem, limita 5
        vistos = set()
        for c in candidatos:
            chave = c.upper()
            if chave not in vistos:
                vistos.add(chave)
                dados.nomes_candidatos.append(c)
            if len(dados.nomes_candidatos) >= 5:
                break
        # Se há um único candidato razoável, usa
        if len(dados.nomes_candidatos) == 1:
            dados.nome = dados.nomes_candidatos[0]
            dados.confianca["nome"] = "media"

    # Default de cidade/estado para Rio Real/BA quando há indício
    if dados.bairro and not dados.cidade:
        dados.cidade = "Rio Real"
        dados.confianca["cidade"] = "baixa"
    if dados.cidade and not dados.estado:
        dados.estado = "BA"
        dados.confianca["estado"] = "baixa"

    return dados
