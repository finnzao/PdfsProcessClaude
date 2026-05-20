"""utils/formatadores.py — Formatadores e normalizadores de strings."""

import re
import unicodedata


def formatar_cpf(cpf: str) -> str:
    """Recebe CPF em qualquer formato; retorna XXX.XXX.XXX-XX ou vazio."""
    if not cpf:
        return ""
    digitos = re.sub(r"\D", "", cpf)
    if len(digitos) != 11:
        return cpf.strip()
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def formatar_telefone(numero: str) -> str:
    """Aceita telefones BR; retorna (DD) NNNNN-NNNN ou (DD) NNNN-NNNN."""
    if not numero:
        return ""
    digitos = re.sub(r"\D", "", numero)
    if digitos.startswith("55") and len(digitos) >= 12:
        digitos = digitos[2:]
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    return numero.strip()


def formatar_data_br(data: str) -> str:
    """Recebe data em varios formatos; retorna DD/MM/AAAA ou vazio."""
    if not data:
        return ""
    m = re.match(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", data.strip())
    if not m:
        return data.strip()
    d, mes, a = m.group(1), m.group(2), m.group(3)
    if len(a) == 2:
        ano_int = int(a)
        a = f"20{a}" if ano_int <= 30 else f"19{a}"
    return f"{int(d):02d}/{int(mes):02d}/{a}"


def _remover_acentos(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar_nome(nome: str) -> str:
    """Remove espacos duplos, normaliza espacamento e capitaliza adequadamente."""
    if not nome:
        return ""
    s = re.sub(r"\s+", " ", nome).strip()
    return titulizar(s)


# Preposicoes e conectivos que permanecem em minusculas em nomes proprios
_PALAVRAS_MINUSCULAS = {"da", "de", "do", "das", "dos", "e", "di", "du", "del", "della"}


def titulizar(s: str) -> str:
    """Title-case respeitando conectivos. 'JOAO DA SILVA' -> 'Joao da Silva'."""
    if not s:
        return ""
    partes = s.strip().split()
    out = []
    for i, palavra in enumerate(partes):
        pl = palavra.lower()
        if i > 0 and pl in _PALAVRAS_MINUSCULAS:
            out.append(pl)
        else:
            out.append(pl.capitalize())
    return " ".join(out)
