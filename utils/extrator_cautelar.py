"""utils/extrator_cautelar.py — Extracao das medidas cautelares aplicadas."""

import re


# Padroes regex de identificacao das cautelares do art. 319 CPP
PADROES_CAUTELAR = {
    "comparecimento_mensal": re.compile(
        r"comparecimento\s+(?:mensal|todo\s+m[êe]s|a\s+cada\s+m[êe]s)",
        re.I,
    ),
    "comparecimento_quinzenal": re.compile(
        r"comparecimento\s+quinzenal|a\s+cada\s+15\s+dias",
        re.I,
    ),
    "comparecimento_periodico": re.compile(
        r"comparecimento\s+peri[óo]dico|comparecer\s+em\s+ju[íi]zo",
        re.I,
    ),
    "proibicao_acesso_local": re.compile(
        r"proibi[çc][ãa]o\s+de\s+acesso|proibido\s+de\s+frequentar|n[ãa]o\s+frequentar",
        re.I,
    ),
    "proibicao_contato_vitima": re.compile(
        r"proibi[çc][ãa]o\s+(?:de\s+)?(?:o\s+)?contato|"
        r"proibido\s+(?:o\s+)?contato|"
        r"n[ãa]o\s+manter\s+contato|"
        r"afastamento\s+da\s+v[íi]tima",
        re.I,
    ),
    "proibicao_ausentar_comarca": re.compile(
        r"proibi[çc][ãa]o\s+de\s+(?:se\s+)?ausentar(?:\s+da)?\s+comarca|n[ãa]o\s+(?:se\s+)?ausentar\s+da\s+comarca",
        re.I,
    ),
    "recolhimento_noturno": re.compile(
        r"recolhimento\s+(?:noturno|domiciliar\s+noturno)",
        re.I,
    ),
    "monitoracao_eletronica": re.compile(
        r"monitora(?:c|çã)o\s+eletr[ôo]nica|tornozeleira",
        re.I,
    ),
    "suspensao_funcao_publica": re.compile(
        r"suspens[ãa]o\s+do\s+exerc[íi]cio\s+(?:de\s+)?fun[çc][ãa]o\s+p[úu]blica",
        re.I,
    ),
    "fianca": re.compile(
        r"\bfian[çc]a\b",
        re.I,
    ),
    "internacao_provisoria": re.compile(
        r"interna[çc][ãa]o\s+provis[óo]ria",
        re.I,
    ),
}


def extrair_cautelares(texto: str) -> dict:
    """
    Identifica quais cautelares foram impostas/aplicadas. Retorna dict com flags
    booleanas e lista de trechos onde foram detectadas.
    """
    out = {k: False for k in PADROES_CAUTELAR}
    out["outras"] = False
    out["trechos"] = []

    if not texto:
        return out

    for chave, padrao in PADROES_CAUTELAR.items():
        m = padrao.search(texto)
        if m:
            out[chave] = True
            ini = max(0, m.start() - 80)
            fim = min(len(texto), m.end() + 80)
            out["trechos"].append({
                "cautelar": chave,
                "trecho": texto[ini:fim].strip(),
            })

    # Sinal de "outras cautelares" quando texto cita art. 319 mas nenhum padrao bateu
    if not any(out[k] for k in PADROES_CAUTELAR) and re.search(
        r"art(?:igo|\.|º)?\s*319", texto, re.I
    ):
        out["outras"] = True

    return out
