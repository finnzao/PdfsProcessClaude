"""
utils/extrator_cautelar.py — Captura estruturada da cautelar.

A cautelar de comparecimento (Art. 319, I CPP) é fixada quase sempre em uma
peça localizada e específica:
    - Audiência de custódia (Art. 310, II CPP): liberdade com cautelar pós-flagrante
    - AIJ com decisão de soltura: revogação de preventiva + cautelar
    - Sentença com pena restritiva ou sursis penal

Este módulo localiza a peça-fonte e extrai:
    - Data da imposição
    - Periodicidade do comparecimento
    - Condições impostas (proibição de aproximação, recolhimento noturno, etc.)
    - Sinais posteriores que cessam a cautelar (revogação, extinção)

A saída alimenta o JSON final e dá ao LLM um diagnóstico pré-pronto sobre
o status: ATIVA, EXTINTA, CONVERTIDA, AMBIGUA.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Optional, List


# ── Patterns de imposição ────────────────────────────────────────

PATTERNS_IMPOSICAO = [
    # Liberdade provisória + cautelar
    re.compile(
        r"\bconcedo\s+(?:a\s+)?liberdade\s+provis[óo]ria"
        r"[\s\S]{0,500}?\b(art\.?\s*319|comparec)",
        re.I,
    ),
    # Cautelar diretamente
    re.compile(
        r"\baplico\s+(?:as?\s+)?medidas?\s+cautelares?\b"
        r"[\s\S]{0,500}?\b(art\.?\s*319|comparec)",
        re.I,
    ),
    # Audiência de custódia
    re.compile(
        r"\baudi[êe]ncia de cust[óo]dia"
        r"[\s\S]{0,800}?\bcomparec",
        re.I,
    ),
    # Sursis processual
    re.compile(
        r"\bsuspens[aã]o condicional do processo"
        r"[\s\S]{0,500}?\bcomparec",
        re.I,
    ),
    # ANPP
    re.compile(
        r"\bacordo de n[aã]o persecu[çc][aã]o penal"
        r"[\s\S]{0,500}?\bcomparec",
        re.I,
    ),
    # Sentença com pena restritiva
    re.compile(
        r"\bsubstitu[íi]o a pena privativa"
        r"[\s\S]{0,500}?\bcomparec",
        re.I,
    ),
]

# Periodicidade
RE_PERIODICIDADE = re.compile(
    r"comparec(?:er|imento)\s+(?:mensal(?:mente)?|bimestral(?:mente)?|"
    r"quinzenal(?:mente)?|semanal(?:mente)?|trimestral(?:mente)?|"
    r"a\s+cada\s+\d+\s+(?:dias|meses|semanas))",
    re.I,
)

RE_PERIODICIDADE_NUMERICA = re.compile(
    r"a\s+cada\s+(\d+)\s+(dias?|meses|semanas)", re.I
)

# Período de prova (sursis/ANPP)
RE_PERIODO_PROVA = re.compile(
    r"per[íi]odo\s+de\s+prova\s+(?:de\s+)?(\d+)\s+(?:anos?|meses)", re.I
)

# Data da decisão
RE_DATA_DECISAO = re.compile(
    r"(?:em|aos?|datad[oa]\s+de|data:?)\s+"
    r"(\d{1,2})[/\-.\s](\d{1,2}|janeiro|fevereiro|mar[çc]o|abril|maio|"
    r"junho|julho|agosto|setembro|outubro|novembro|dezembro)"
    r"[/\-.\s]+(\d{4})",
    re.I,
)

# Padrão de data por extenso típico de atas: "Aos X dias do mês de Y de ZZZZ"
RE_DATA_EXTENSO = re.compile(
    r"\baos?\s+(\d{1,2})\s+dias?\s+do\s+m[êe]s\s+de\s+"
    r"(janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})",
    re.I,
)

# ── Patterns de cessação ─────────────────────────────────────────

PATTERNS_CESSACAO = {
    "REVOGACAO_EXPRESSA": re.compile(
        r"\brevogo\s+as?\s+(?:medidas?\s+)?cautelares?\b", re.I,
    ),
    "EXTINCAO_PUNIBILIDADE": re.compile(
        r"\bdeclaro\s+extinta\s+a\s+punibilidade\b|"
        r"\bextin[gç]o\s+a\s+punibilidade\b",
        re.I,
    ),
    "CUMPRIMENTO_SURSIS": re.compile(
        r"\bcumprido\s+o\s+per[íi]odo\s+de\s+prova\b|"
        r"\bart\.?\s*89[\s,]+§\s*5",
        re.I,
    ),
    "CUMPRIMENTO_ANPP": re.compile(
        r"\bcumpridas?\s+as?\s+condi[çc][õo]es\b[\s\S]{0,200}\banpp\b|"
        r"\bart\.?\s*28[-\s]?a[\s,]+§\s*13",
        re.I,
    ),
    "CONVERSAO_PREVENTIVA": re.compile(
        r"\bdecreto\s+(?:a\s+)?pris[aã]o\s+preventiva\b|"
        r"\bconverto\s+em\s+pris[aã]o\s+preventiva\b",
        re.I,
    ),
    "ABSOLVICAO_TRANSITADA": re.compile(
        r"\babsolvo\s+o\s+r[ée]u\b[\s\S]{0,2000}\btransit", re.I,
    ),
}

# Sinais de homologação (criam cautelar) sem prova de cumprimento
PATTERNS_HOMOLOGACAO = {
    "SURSIS_HOMOLOGADO": re.compile(
        r"\bsursi[s]?\s+processual\b|"
        r"\bsuspens[aã]o\s+condicional\s+do\s+processo\b|"
        r"\bart\.?\s*89\s*(?:da\s*)?lei\s*9[.\s]?099",
        re.I,
    ),
    "ANPP_HOMOLOGADO": re.compile(
        r"\bhomologo?\s+o?\s*acordo\s+de\s+n[aã]o\s+persecu[çc][aã]o\b|"
        r"\bhomologo?\s+(?:o\s+)?anpp\b",
        re.I,
    ),
    "TRANSACAO_HOMOLOGADA": re.compile(
        r"\bhomologo?\s+(?:a\s+)?transa[çc][aã]o\s+penal\b", re.I,
    ),
}


# ── Modelo ───────────────────────────────────────────────────────

@dataclass
class DadosCautelar:
    """Resumo estruturado da cautelar de comparecimento."""

    # Status final
    status: str = "INDEFINIDO"
    # ATIVA, EXTINTA_REVOGACAO, EXTINTA_CUMPRIMENTO,
    # EXTINTA_ABSOLVICAO, CONVERTIDA_PREVENTIVA,
    # SUSPEITA_ATIVA, AMBIGUA, NUNCA_IMPOSTA

    motivo_status: str = ""

    # Imposição
    imposta: bool = False
    peca_fonte: str = ""           # Tipo da peça onde foi imposta
    pagina_fonte: str = ""         # "p.45-48"
    doc_id_fonte: str = ""         # "Num. 440867200"
    data_imposicao: str = ""       # "15/03/2024"
    periodicidade: str = ""        # "mensal", "bimestral", "a cada 60 dias"
    periodo_prova: str = ""        # "2 anos" (sursis/ANPP)

    # Condições adicionais
    condicoes: List[str] = field(default_factory=list)

    # Cessação
    cessada: bool = False
    motivo_cessacao: str = ""      # "revogação expressa", "cumprimento", etc.
    data_cessacao: str = ""

    # Diagnóstico para humano/LLM
    sinalizadores: List[str] = field(default_factory=list)
    confianca: str = "baixa"       # "alta", "media", "baixa"

    def to_dict(self) -> dict:
        return asdict(self)


# ── Helpers ──────────────────────────────────────────────────────

MESES = {
    "janeiro": "01", "fevereiro": "02", "março": "03", "marco": "03",
    "abril": "04", "maio": "05", "junho": "06", "julho": "07",
    "agosto": "08", "setembro": "09", "outubro": "10",
    "novembro": "11", "dezembro": "12",
}


def _normalizar_data(d: str, m: str, a: str) -> str:
    m_lower = m.lower()
    if m_lower in MESES:
        m = MESES[m_lower]
    return f"{int(d):02d}/{int(m):02d}/{a}"


def _extrair_secoes(md: str) -> list[dict]:
    secoes = []
    pattern = re.compile(r"^##\s+([A-ZÁ-ÚÇ_ ]+)\s*\(([^)]+)\)(?:\s*—\s*([^\n]+))?", re.M)
    matches = list(pattern.finditer(md))
    for i, m in enumerate(matches):
        tipo = m.group(1).strip()
        paginas = m.group(2).strip()
        ids = (m.group(3) or "").strip()
        inicio = m.end()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        texto = md[inicio:fim].strip()
        secoes.append({"tipo": tipo, "paginas": paginas, "doc_ids": ids, "texto": texto})
    return secoes


def _extrair_periodicidade(texto: str) -> str:
    """Captura periodicidade em forma normalizada."""
    m = RE_PERIODICIDADE.search(texto)
    if m:
        per = m.group(0).lower()
        if "mensal" in per:
            return "mensal"
        if "bimestral" in per:
            return "bimestral"
        if "quinzenal" in per:
            return "quinzenal"
        if "semanal" in per:
            return "semanal"
        if "trimestral" in per:
            return "trimestral"

    m_num = RE_PERIODICIDADE_NUMERICA.search(texto)
    if m_num:
        n = m_num.group(1)
        unidade = m_num.group(2).lower()
        return f"a cada {n} {unidade}"

    return ""


def _extrair_data(texto: str) -> str:
    """Primeira data válida no texto. Tenta formato numérico, depois extenso."""
    m = RE_DATA_DECISAO.search(texto)
    if m:
        return _normalizar_data(m.group(1), m.group(2), m.group(3))
    m_ext = RE_DATA_EXTENSO.search(texto)
    if m_ext:
        return _normalizar_data(m_ext.group(1), m_ext.group(2), m_ext.group(3))
    return ""


def _extrair_condicoes(texto: str) -> list[str]:
    """Identifica condições típicas do Art. 319."""
    condicoes = []
    mapa = {
        "Comparecimento periódico": r"\bcomparec(?:er|imento)\s+(?:mensal|bimestral|peri[óo]dic)",
        "Proibição de aproximação": r"\bproibi[çc][aã]o\s+de\s+aproxim",
        "Proibição de contato": r"\bproibi[çc][aã]o\s+de\s+contato\b",
        "Proibição de ausentar-se": r"\bproibi[çc][aã]o\s+de\s+ausentar",
        "Recolhimento domiciliar noturno": r"\brecolhimento\s+domiciliar\s+noturno",
        "Suspensão de função pública": r"\bsuspens[aã]o\s+(?:de\s+)?fun[çc][aã]o\s+p[úu]blica",
        "Fiança": r"\bfian[çc]a\b",
        "Monitoração eletrônica": r"\bmonitora[çc][aã]o\s+eletr[ôo]nica|tornozeleira",
    }
    for nome, pat in mapa.items():
        if re.search(pat, texto, re.I):
            condicoes.append(nome)
    return condicoes


# ── Função principal ─────────────────────────────────────────────

# Peças onde a cautelar costuma ser fixada, em ordem de prioridade
PECAS_FIXACAO = [
    "AUDIENCIA_CUSTODIA",
    "LIBERDADE_PROVISORIA",
    "CAUTELAR_319",
    "TERMO_COMPROMISSO",
    "ATA",
    "DECISÃO",
    "SURSIS_PROCESSUAL",
    "ANPP",
    "TRANSACAO_PENAL",
]


def extrair_cautelar(md_completo: str) -> DadosCautelar:
    """
    Diagnóstico estruturado da cautelar a partir do markdown.

    Retorna DadosCautelar com status preliminar — o LLM pode revisar
    com base em ambiguidades sinalizadas.
    """
    dados = DadosCautelar()
    secoes = _extrair_secoes(md_completo)

    if not secoes:
        dados.status = "NUNCA_IMPOSTA"
        dados.motivo_status = "Não foi possível segmentar peças do markdown"
        return dados

    # Indexa por tipo
    secoes_por_tipo: dict[str, list[dict]] = {}
    for s in secoes:
        secoes_por_tipo.setdefault(s["tipo"], []).append(s)

    # ── Fase 1: localizar imposição ──
    peca_imposicao = None
    for tipo_pri in PECAS_FIXACAO:
        for s in secoes_por_tipo.get(tipo_pri, []):
            # Verifica se a peça contém sinais de imposição da cautelar
            tem_imposicao = any(p.search(s["texto"]) for p in PATTERNS_IMPOSICAO)
            tem_periodicidade = bool(RE_PERIODICIDADE.search(s["texto"]))
            if tem_imposicao or tem_periodicidade:
                peca_imposicao = s
                dados.peca_fonte = tipo_pri
                dados.pagina_fonte = s["paginas"]
                dados.doc_id_fonte = s["doc_ids"]
                break
        if peca_imposicao:
            break

    if peca_imposicao:
        dados.imposta = True
        dados.periodicidade = _extrair_periodicidade(peca_imposicao["texto"])
        dados.data_imposicao = _extrair_data(peca_imposicao["texto"][:1000])
        dados.condicoes = _extrair_condicoes(peca_imposicao["texto"])

        m_prova = RE_PERIODO_PROVA.search(peca_imposicao["texto"])
        if m_prova:
            dados.periodo_prova = f"{m_prova.group(1)} anos"

        dados.confianca = "alta" if dados.periodicidade else "media"

    # ── Fase 2: detectar cessação posterior ──
    # Procura sinais em qualquer lugar do markdown — mas idealmente DEPOIS
    # da peça de imposição (heurística: ordem das peças no markdown)
    motivos_cessacao: list[str] = []
    for nome, pat in PATTERNS_CESSACAO.items():
        m = pat.search(md_completo)
        if m:
            motivos_cessacao.append(nome)
            dados.cessada = True
            if not dados.data_cessacao:
                dados.data_cessacao = _extrair_data(
                    md_completo[max(0, m.start() - 200):m.end() + 200]
                )

    # ── Fase 3: definir status final ──
    if not dados.imposta:
        # Verifica homologação de instituto que cria cautelar
        homologou = False
        for nome, pat in PATTERNS_HOMOLOGACAO.items():
            if pat.search(md_completo):
                homologou = True
                dados.sinalizadores.append(f"Homologação detectada: {nome}")
                break

        if homologou and not dados.cessada:
            dados.status = "SUSPEITA_ATIVA"
            dados.motivo_status = (
                "Detectada homologação de sursis/ANPP/transação sem prova de "
                "cumprimento integral. Verificar se período de prova já se encerrou."
            )
            dados.confianca = "baixa"
            dados.imposta = True  # pressupõe cautelar implícita
        else:
            dados.status = "NUNCA_IMPOSTA"
            dados.motivo_status = "Sem peça de imposição de cautelar identificada"
        return dados

    # Imposta: classificar com base nos motivos de cessação
    if "ABSOLVICAO_TRANSITADA" in motivos_cessacao:
        dados.status = "EXTINTA_ABSOLVICAO"
        dados.motivo_status = "Réu absolvido com trânsito em julgado"
        dados.motivo_cessacao = "absolvição transitada"
    elif "CUMPRIMENTO_SURSIS" in motivos_cessacao:
        dados.status = "EXTINTA_CUMPRIMENTO"
        dados.motivo_status = "Sursis processual cumprido (Art. 89 §5º Lei 9.099)"
        dados.motivo_cessacao = "cumprimento sursis"
    elif "CUMPRIMENTO_ANPP" in motivos_cessacao:
        dados.status = "EXTINTA_CUMPRIMENTO"
        dados.motivo_status = "ANPP cumprido (Art. 28-A §13 CPP)"
        dados.motivo_cessacao = "cumprimento ANPP"
    elif "EXTINCAO_PUNIBILIDADE" in motivos_cessacao:
        dados.status = "EXTINTA_PUNIBILIDADE"
        dados.motivo_status = "Punibilidade declarada extinta"
        dados.motivo_cessacao = "extinção punibilidade"
    elif "REVOGACAO_EXPRESSA" in motivos_cessacao:
        dados.status = "EXTINTA_REVOGACAO"
        dados.motivo_status = "Cautelares revogadas expressamente"
        dados.motivo_cessacao = "revogação expressa"
    elif "CONVERSAO_PREVENTIVA" in motivos_cessacao:
        dados.status = "CONVERTIDA_PREVENTIVA"
        dados.motivo_status = "Cautelar convertida em prisão preventiva"
        dados.motivo_cessacao = "preventiva decretada"
    else:
        # Sem cessação detectada: cautelar provavelmente ATIVA,
        # mas sinaliza ambiguidades importantes
        dados.status = "ATIVA"
        dados.motivo_status = (
            f"Cautelar imposta em {dados.data_imposicao or 'data não localizada'} "
            f"({dados.peca_fonte}, {dados.pagina_fonte}). "
            f"Sem decisão posterior de cessação encontrada nos autos."
        )

        # Sinalizadores que pedem revisão humana mesmo sendo ATIVA
        if dados.peca_fonte in ("SURSIS_PROCESSUAL", "ANPP", "TRANSACAO_PENAL"):
            dados.sinalizadores.append(
                "Instituto consensual: verificar se período de prova já encerrou"
            )
            dados.confianca = "baixa"
        if not dados.periodicidade:
            dados.sinalizadores.append(
                "Periodicidade não localizada na peça-fonte"
            )
            dados.confianca = "baixa"
        if not dados.data_imposicao:
            dados.sinalizadores.append("Data de imposição não localizada")

    return dados
