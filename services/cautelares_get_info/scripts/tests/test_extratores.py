"""Testes dos extratores utilitarios (cautelar e qualificacao)."""

import unittest

from utils.extrator_cautelar import extrair_cautelares
from utils.extrator_qualificacao import extrair_qualificacao
from utils.formatadores import (
    formatar_cpf,
    formatar_telefone,
    formatar_data_br,
    titulizar,
)
from utils.tipos_pecas import normalizar_tipo_peca


class TestFormatadores(unittest.TestCase):
    def test_cpf_valido(self):
        self.assertEqual(formatar_cpf("12345678901"), "123.456.789-01")

    def test_cpf_ja_formatado(self):
        self.assertEqual(formatar_cpf("123.456.789-01"), "123.456.789-01")

    def test_cpf_invalido_devolve_strip(self):
        self.assertEqual(formatar_cpf("123"), "123")

    def test_telefone_11_digitos(self):
        self.assertEqual(formatar_telefone("11987654321"), "(11) 98765-4321")

    def test_telefone_10_digitos(self):
        self.assertEqual(formatar_telefone("1133334444"), "(11) 3333-4444")

    def test_telefone_com_ddi(self):
        self.assertEqual(formatar_telefone("5511987654321"), "(11) 98765-4321")

    def test_data_br_formatos_variados(self):
        self.assertEqual(formatar_data_br("01/02/2024"), "01/02/2024")
        self.assertEqual(formatar_data_br("1-2-2024"), "01/02/2024")
        self.assertEqual(formatar_data_br("01.02.2024"), "01/02/2024")

    def test_data_br_ano_2_digitos(self):
        # ano <=30 vira 20XX
        self.assertEqual(formatar_data_br("01/02/24"), "01/02/2024")
        # ano >30 vira 19XX
        self.assertEqual(formatar_data_br("01/02/85"), "01/02/1985")

    def test_titulizar_respeita_conectivos(self):
        self.assertEqual(titulizar("JOAO DA SILVA"), "Joao da Silva")
        self.assertEqual(titulizar("MARIA DOS SANTOS"), "Maria dos Santos")


class TestNormalizarTipoPeca(unittest.TestCase):
    def test_aliases_comuns(self):
        self.assertEqual(normalizar_tipo_peca("denuncia"), "DENUNCIA")
        self.assertEqual(normalizar_tipo_peca("denúncia"), "DENUNCIA")
        self.assertEqual(normalizar_tipo_peca("BO"), "BOLETIM_OCORRENCIA")
        self.assertEqual(normalizar_tipo_peca("APF"), "AUTO_PRISAO_FLAGRANTE")
        self.assertEqual(normalizar_tipo_peca("sentença"), "SENTENCA")

    def test_canonico_passa_direto(self):
        self.assertEqual(normalizar_tipo_peca("DENUNCIA"), "DENUNCIA")

    def test_desconhecido_vira_doc(self):
        self.assertEqual(normalizar_tipo_peca("qualquer-coisa"), "DOC")
        self.assertEqual(normalizar_tipo_peca(""), "DOC")


class TestExtrairCautelares(unittest.TestCase):
    def test_comparecimento_mensal(self):
        r = extrair_cautelares("o reu devera fazer comparecimento mensal ao juizo")
        self.assertTrue(r["comparecimento_mensal"])

    def test_proibicao_contato_vitima(self):
        r = extrair_cautelares("Fica proibido o contato com a vitima Maria")
        self.assertTrue(r["proibicao_contato_vitima"])

    def test_monitoracao_eletronica(self):
        r = extrair_cautelares("Determino o uso de tornozeleira eletronica")
        self.assertTrue(r["monitoracao_eletronica"])

    def test_fianca(self):
        r = extrair_cautelares("Arbitra-se fianca no valor de R$ 5.000,00")
        self.assertTrue(r["fianca"])

    def test_outras_quando_cita_319_sem_padrao_especifico(self):
        r = extrair_cautelares("Aplico medida do art. 319 do CPP em condicoes a serem definidas")
        self.assertTrue(r["outras"])

    def test_texto_vazio(self):
        r = extrair_cautelares("")
        self.assertFalse(any(v for k, v in r.items() if isinstance(v, bool)))

    def test_trechos_capturados(self):
        r = extrair_cautelares("Recolhimento noturno no periodo das 22h as 6h")
        self.assertTrue(r["recolhimento_noturno"])
        self.assertEqual(len(r["trechos"]), 1)
        self.assertIn("Recolhimento", r["trechos"][0]["trecho"])


class TestExtrairQualificacao(unittest.TestCase):
    def test_extrai_nome_e_cpf(self):
        texto = "Nome: JOAO DA SILVA SANTOS\nCPF: 12345678901\nRG: 1234567 SSP/BA"
        r = extrair_qualificacao(texto)
        self.assertEqual(r["nome"], "Joao da Silva Santos")
        self.assertEqual(r["cpf"], "123.456.789-01")
        self.assertIn("1234567", r["rg"])

    def test_extrai_data_nascimento_e_filiacao(self):
        texto = (
            "Nome: MARIA SANTOS\n"
            "Data de nascimento: 15/03/1990\n"
            "Mae: ANA SANTOS\n"
        )
        r = extrair_qualificacao(texto)
        self.assertEqual(r["data_nascimento"], "15/03/1990")
        self.assertEqual(r["filiacao_mae"], "Ana Santos")

    def test_extrai_telefone(self):
        texto = "Nome: TESTE\nTelefone: (71) 98765-4321"
        r = extrair_qualificacao(texto)
        self.assertEqual(r["telefone"], "(71) 98765-4321")

    def test_texto_vazio(self):
        r = extrair_qualificacao("")
        self.assertEqual(r["nome"], "")
        self.assertEqual(r["cpf"], "")


if __name__ == "__main__":
    unittest.main()
