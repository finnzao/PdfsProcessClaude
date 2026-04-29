"""
utils/formatadores.py — Helpers de formatação reutilizáveis.

Funções pequenas usadas em vários pontos do pipeline:
formatação de CPF/CEP/telefone, extração do número CNJ a partir do nome do arquivo,
e captura da primeira linha significativa de um texto.
"""

import re
from pathlib import Path


def formatar_cpf(cpf: str | None) -> str:
    """
    Formata CPF para 000.000.000-00.

    Aceita: '12345678900', '123.456.789-00', '123 456 789 00', None.
    Retorna string vazia se inválido.

    >>> formatar_cpf('12345678900')
    '123.456.789-00'
    >>> formatar_cpf('123.456.789-00')
    '123.456.789-00'
    >>> formatar_cpf(None)
    ''
    """
    if not cpf:
        return ''
    digitos = re.sub(r'\D', '', cpf)
    if len(digitos) != 11:
        return cpf.strip()  # devolve original se não tem 11 dígitos
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def formatar_telefone(tel: str | None) -> str:
    """
    Formata telefone brasileiro para (DDD) XXXXX-XXXX ou (DDD) XXXX-XXXX.

    >>> formatar_telefone('75999999999')
    '(75) 99999-9999'
    >>> formatar_telefone('7533334444')
    '(75) 3333-4444'
    """
    if not tel:
        return ''
    digitos = re.sub(r'\D', '', tel)
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    return tel.strip()


def formatar_cep(cep: str | None) -> str:
    """
    Formata CEP para 00000-000.

    >>> formatar_cep('48340000')
    '48340-000'
    """
    if not cep:
        return ''
    digitos = re.sub(r'\D', '', cep)
    if len(digitos) != 8:
        return cep.strip()
    return f"{digitos[:5]}-{digitos[5:]}"


def primeira_linha(texto: str, max_chars: int = 120) -> str:
    """
    Retorna a primeira linha 'significativa' de um texto.
    Útil para gerar resumos de peças classificadas como RESUMO.

    >>> primeira_linha("# Cabeçalho\\n\\nConteúdo significativo aqui")
    'Conteúdo significativo aqui'
    """
    for linha in texto.split('\n'):
        limpa = linha.strip().strip('#').strip('*').strip()
        if len(limpa) > 10:
            return limpa[:max_chars]
    return texto[:max_chars]


def extrair_numero_processo(nome_arquivo: str) -> str:
    """
    Extrai o número CNJ (formato 0000000-00.0000.0.00.0000) do nome de um
    arquivo de PDF ou MD.

    Aceita várias variações de nomenclatura usadas no PJe/TJBA.

    >>> extrair_numero_processo("0001234-56.2024.8.05.0216.pdf")
    '0001234-56.2024.8.05.0216'
    >>> extrair_numero_processo("0001234_56_2024_8_05_0216.md")
    '0001234-56.2024.8.05.0216'
    """
    padrao = re.search(
        r'(\d{7})[-_.]?(\d{2})[_.](\d{4})[_.](\d{1,2})[_.](\d{2})[_.](\d{4})',
        nome_arquivo,
    )
    if padrao:
        return (
            f"{padrao.group(1)}-{padrao.group(2)}."
            f"{padrao.group(3)}.{padrao.group(4)}."
            f"{padrao.group(5)}.{padrao.group(6)}"
        )
    return Path(nome_arquivo).stem


def formatar_doc_ids(doc_ids: list) -> str:
    """
    Formata lista de IDs PJe para exibição no cabeçalho da peça.

    >>> formatar_doc_ids([('440866922', '1'), ('440866922', '2')])
    'Num. 440866922 - Pág. 1, Num. 440866922 - Pág. 2'
    """
    if not doc_ids:
        return ""
    return ", ".join(f"Num. {n} - Pág. {p}" for n, p in doc_ids)
