"""utils/constantes_pje.py — Constantes do dominio PJe/TJBA."""

# UFs brasileiras
UF_BR = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


# Tipos de cautelares previstas no art. 319 do CPP e correlatas
TIPOS_CAUTELARES_LISTA = [
    "comparecimento_mensal",
    "comparecimento_quinzenal",
    "comparecimento_periodico",
    "proibicao_acesso_local",
    "proibicao_contato_vitima",
    "proibicao_ausentar_comarca",
    "recolhimento_noturno",
    "monitoracao_eletronica",
    "suspensao_funcao_publica",
    "fianca",
    "internacao_provisoria",
    "outras",
]


# Prazo padrao do termo de comparecimento (em dias)
PRAZO_TERMO_DIAS = 30


# Regexes auxiliares para extracao de qualificacao do reu
REGEXES_QUALIFICACAO = {
    "nome": r"(?:Nome|N[oO]ME)[:.\s]+([A-ZÁ-Ú][A-Za-zÁ-Úá-ú\s.'\-]{4,80}?)(?=\s*\n|\s*$)",
    "alcunha": r"(?:Alcunha|Vulgo|Apelido)[:.\s]+([^\n]{2,40})",
    "cpf": r"\b(\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b",
    "rg": r"(?:RG|R\.G\.|Identidade)[:.\s]+([\d.\-]+(?:\s*[/-]?\s*[A-Z]{2,5})?)",
    "data_nascimento": (
        r"(?:Data\s+de\s+nascimento|Nasc(?:ido|imento)?(?:\s+em)?)[:.\s]+"
        r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})"
    ),
    "filiacao_mae": r"(?:M[ãa]e|Filiac[ãa]o materna)[:.\s]+([A-ZÁ-Ú][A-Za-zÁ-Úá-ú\s.'\-]{4,80}?)(?=\s*\n|\s*$)",
    "filiacao_pai": r"(?:Pai|Filiac[ãa]o paterna)[:.\s]+([A-ZÁ-Ú][A-Za-zÁ-Úá-ú\s.'\-]{4,80}?)(?=\s*\n|\s*$)",
    "endereco": (
        r"(?:Endere[çc]o|Residente\s+(?:na?|em))[:.\s]+"
        r"([A-Za-zÁ-Úá-ú0-9,\s.'\-º°ºª/]{10,160})"
    ),
    "telefone": r"\(?\b(\d{2})\)?\s*((?:9\s*\d{4})|(?:\d{4,5}))\s*[-.\s]?\s*(\d{4})\b",
    "profissao": r"(?:Profiss[ãa]o|Ocupa[çc][ãa]o)[:.\s]+([A-Za-zÁ-Úá-ú\s.'\-]{3,40})",
    "estado_civil": r"(?:Estado\s+civil)[:.\s]+(solteir[oa]|casad[oa]|divorciad[oa]|viuv[oa]|vi[uú]v[oa]|uni[ãa]o\s+est[áa]vel|amasiad[oa])",
    "naturalidade": r"(?:Natural\s+de|Naturalidade)[:.\s]+([A-Za-zÁ-Úá-ú\s.\-/]{3,60})",
    "escolaridade": (
        r"(?:Escolaridade|Instru[çc][ãa]o)[:.\s]+"
        r"([A-Za-zÁ-Úá-ú\s.\-]{3,60})"
    ),
}
