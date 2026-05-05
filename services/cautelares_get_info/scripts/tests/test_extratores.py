"""
test_extratores.py — Teste rápido de sanidade dos extratores.
Roda em alguns segundos. Não substitui pytest, mas valida que o pipeline
inteiro processa um markdown sintético e produz a saída esperada.

Roda a partir da raiz do projeto:
    python -m services.cautelares_get_info.scripts.tests.test_extratores
ou diretamente:
    python services/cautelares_get_info/scripts/tests/test_extratores.py
"""

import sys
import json
from pathlib import Path

# Sobe 4 níveis: tests/ → scripts/ → cautelares_get_info/ → services/ → raiz
RAIZ_PROJETO = Path(__file__).resolve().parents[4]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from utils.extrator_qualificacao import extrair_qualificacao_reu
from utils.extrator_cautelar import extrair_cautelar
from utils.tipos_pecas import classificar_peca

MD_SINTETICO = """# 8001234-56.2024.8.05.0216
**Classe:** APOrd
**Assunto:** Roubo Majorado
**Órgão julgador:** Vara Criminal de Rio Real
**Réu/Executado:** JOAO DA SILVA SANTOS
**Total de páginas:** 45
**Peças identificadas:** 8

---

## BO (p.1-3) — Num. 440866900 (p.1-3)

Boletim de Ocorrência Nº 12345/2024

Qualificação do(a) Indiciado(a):
Nome: JOAO DA SILVA SANTOS
CPF: 123.456.789-00
RG: 12.345.678 SSP/BA
Filiação: Maria da Silva Santos e José da Silva Santos
Data de nascimento: 15/05/1990
Naturalidade: Rio Real/BA
Nacionalidade: Brasileira
Estado civil: Solteiro
Profissão: Pedreiro
Escolaridade: Fundamental incompleto
Telefone: (75) 99999-1234
Endereço: Rua das Flores, 123, Centro, Rio Real/BA, CEP: 48340-000

Vítima:
Nome: MARIA OLIVEIRA
CPF: 987.654.321-00
Telefone: (75) 98888-4321

## DENÚNCIA (p.5-7) — Num. 440866922 (p.1-3)

O MINISTÉRIO PÚBLICO DO ESTADO DA BAHIA, vem oferecer a presente DENÚNCIA
em face de:

JOAO DA SILVA SANTOS, brasileiro, solteiro, pedreiro, RG 12.345.678 SSP/BA,
CPF 123.456.789-00, residente na Rua das Flores, 123, Centro, Rio Real/BA.

Como incurso nas sanções do Art. 157, §2º-A, do Código Penal.

## AUDIENCIA_CUSTODIA (p.10-15) — Num. 440867200 (p.1-6)

Aos 16 dias do mês de março de 2024, realizada a audiência de custódia
do conduzido JOAO DA SILVA SANTOS.

Presentes o Ministério Público e o Defensor Público.

DECISÃO:

Concedo liberdade provisória ao conduzido, nos termos do Art. 321 do CPP,
mediante as seguintes medidas cautelares (Art. 319 CPP):

I — comparecimento mensal ao juízo;
III — proibição de contato com a vítima;
IV — proibição de ausentar-se da comarca por mais de 7 dias.

Expeça-se alvará de soltura.

## DESPACHO (p.20) — Num. 440868000 (p.1)

Cite-se o réu para apresentar resposta à acusação no prazo legal.
"""


# ── Caso 2: sursis processual homologado SEM cumprimento ─────────

MD_SURSIS_PENDENTE = """# 8002345-67.2023.8.05.0216
**Classe:** APSum
**Assunto:** Lesão Corporal Leve
**Réu/Executado:** ANA MARIA OLIVEIRA

---

## DENÚNCIA (p.3-5) — Num. 440877000 (p.1-3)

Indiciado: ANA MARIA OLIVEIRA, CPF 222.333.444-55, residente em Rio Real/BA.

## SURSIS_PROCESSUAL (p.20-22) — Num. 440878000 (p.1-3)

Em audiência designada para o art. 89 da Lei 9.099/95, foi proposta e aceita
a suspensão condicional do processo.

Período de prova: 2 anos.

Condições:
- Comparecimento mensal ao juízo;
- Não ausentar-se da comarca por mais de 7 dias sem autorização;
- Reparar o dano à vítima no prazo de 60 dias.

Suspendo o processo. Aguarde-se cumprimento.

Data: 10/03/2023.
"""


def test_classificar():
    print("\n── Teste: classificar_peca ──")
    casos = [
        ("OFEREÇO A PRESENTE DENÚNCIA contra Fulano", "DENÚNCIA"),
        ("Concedo liberdade provisória ao conduzido, nos termos do Art. 321 do CPP", "LIBERDADE_PROVISORIA"),
        ("Audiência de custódia realizada na presença do MP", "AUDIENCIA_CUSTODIA"),
        ("Cumprido o período de prova, declaro extinta a punibilidade", "CUMPRIMENTO_SURSIS"),
        ("Boletim de Ocorrência Nº 12345/2024", "BO"),
        ("Suspensão condicional do processo, art. 89 da Lei 9.099", "SURSIS_PROCESSUAL"),
        ("DECRETO A PRISÃO PREVENTIVA do réu", "PREVENTIVA"),
    ]
    ok = 0
    for texto, esperado in casos:
        tipo, score = classificar_peca(texto)
        sucesso = tipo == esperado
        if sucesso:
            ok += 1
        print(f"  {'✓' if sucesso else '✗'} {esperado:25} got={tipo:25} score={score}")
    print(f"  Total: {ok}/{len(casos)}")
    return ok == len(casos)


def test_qualificacao():
    print("\n── Teste: extrair_qualificacao_reu (caso completo) ──")
    dados = extrair_qualificacao_reu(MD_SINTETICO)
    print(f"  Nome:         {dados.nome}")
    print(f"  CPF:          {dados.cpf}")
    print(f"  RG:           {dados.rg}")
    print(f"  Mãe:          {dados.nome_mae}")
    print(f"  Pai:          {dados.nome_pai}")
    print(f"  Nascimento:   {dados.data_nascimento}")
    print(f"  Naturalidade: {dados.naturalidade}")
    print(f"  Estado civil: {dados.estado_civil}")
    print(f"  Profissão:    {dados.profissao}")
    print(f"  Telefone:     {dados.telefone}")
    print(f"  CEP:          {dados.cep}")
    print(f"  Logradouro:   {dados.logradouro}")
    print(f"  Cidade:       {dados.cidade}")
    print(f"  Campos preenchidos: {dados.campos_preenchidos()}/18")

    # Asserções importantes
    erros = []
    if "JOAO" not in dados.nome.upper():
        erros.append(f"nome esperado JOAO DA SILVA, got: {dados.nome}")
    if dados.cpf != "123.456.789-00":
        erros.append(f"CPF errado: {dados.cpf}")
    # Crítico: NÃO deve ter capturado o CPF da vítima (987.654.321-00)
    if "987" in dados.cpf:
        erros.append("CPF da VÍTIMA foi capturado como sendo do réu — falha grave")
    # Telefone não deve ser o da vítima
    if "8888" in dados.telefone:
        erros.append("telefone da vítima foi capturado")

    if erros:
        for e in erros:
            print(f"  ✗ {e}")
        return False
    print("  ✓ Sem mistura réu/vítima")
    return True


def test_cautelar_ativa():
    print("\n── Teste: extrair_cautelar (cautelar ATIVA) ──")
    dados = extrair_cautelar(MD_SINTETICO)
    print(f"  Status:           {dados.status}")
    print(f"  Imposta:          {dados.imposta}")
    print(f"  Peça-fonte:       {dados.peca_fonte}")
    print(f"  Periodicidade:    {dados.periodicidade}")
    print(f"  Data imposição:   {dados.data_imposicao}")
    print(f"  Condições:        {dados.condicoes}")
    print(f"  Confiança:        {dados.confianca}")

    erros = []
    if dados.status != "ATIVA":
        erros.append(f"status esperado ATIVA, got: {dados.status}")
    if dados.periodicidade != "mensal":
        erros.append(f"periodicidade: {dados.periodicidade}")
    if not dados.imposta:
        erros.append("deveria estar imposta")

    if erros:
        for e in erros:
            print(f"  ✗ {e}")
        return False
    print("  ✓ Cautelar ATIVA detectada corretamente")
    return True


def test_cautelar_suspeita():
    print("\n── Teste: extrair_cautelar (sursis sem cumprimento → SUSPEITA_ATIVA) ──")
    dados = extrair_cautelar(MD_SURSIS_PENDENTE)
    print(f"  Status:           {dados.status}")
    print(f"  Periodicidade:    {dados.periodicidade}")
    print(f"  Período prova:    {dados.periodo_prova}")
    print(f"  Confiança:        {dados.confianca}")
    print(f"  Sinalizadores:    {dados.sinalizadores}")

    if dados.status not in ("ATIVA", "SUSPEITA_ATIVA"):
        print(f"  ✗ esperado ATIVA ou SUSPEITA_ATIVA, got: {dados.status}")
        return False
    if not dados.imposta:
        print("  ✗ deveria estar imposta (sursis cria cautelar)")
        return False
    print("  ✓ Sursis sem cumprimento foi tratado como ainda ativo")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("  Testes de sanidade — extractores SCC v2")
    print("=" * 60)

    resultados = [
        test_classificar(),
        test_qualificacao(),
        test_cautelar_ativa(),
        test_cautelar_suspeita(),
    ]

    print("\n" + "=" * 60)
    if all(resultados):
        print(f"  TODOS OS TESTES PASSARAM ({sum(resultados)}/{len(resultados)})")
        sys.exit(0)
    else:
        print(f"  FALHAS: {len(resultados) - sum(resultados)}/{len(resultados)}")
        sys.exit(1)
