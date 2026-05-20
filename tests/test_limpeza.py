"""
tests/test_limpeza.py — Limpeza e extrair_doc_id.

Cobre:
  - Remocao de padroes institucionais (assinatura, URL, codigos PJe)
  - Regex nao-gananciosas (nao engolem conteudo util)
  - Preservacao do doc_id antes da limpeza
  - Modo verbose com debug_log
  - Padroes ampliados: Num., Documento nº, Id., ID:
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from common.limpeza_pje import (
    PADROES_LIXO,
    extrair_doc_id,
    limpar_texto,
)


class TestExtrairDocId(unittest.TestCase):

    def test_num_pag_padrao(self):
        r = extrair_doc_id("texto Num. 440866922 - Pág. 5 fim")
        self.assertEqual(r, ("440866922", "5"))

    def test_variante_documento_n(self):
        r = extrair_doc_id("blah Documento nº 12345678 - Pag. 3 blah")
        self.assertIsNotNone(r)
        self.assertEqual(r[0], "12345678")

    def test_variante_id(self):
        r = extrair_doc_id("contexto ID: 999888 outro")
        self.assertIsNotNone(r)
        self.assertEqual(r[0], "999888")

    def test_variante_id_ponto(self):
        r = extrair_doc_id("trecho Id. 4441122 final")
        self.assertIsNotNone(r)
        self.assertEqual(r[0], "4441122")

    def test_ultimo_quando_multiplos(self):
        # Rodape: deve pegar o ultimo (IDs com 5+ digitos)
        t = "Num. 11111 - Pág. 1\nmuito texto\nNum. 99999 - Pág. 7"
        r = extrair_doc_id(t)
        self.assertEqual(r, ("99999", "7"))

    def test_sem_match(self):
        self.assertIsNone(extrair_doc_id("texto totalmente neutro"))

    def test_string_vazia(self):
        self.assertIsNone(extrair_doc_id(""))


class TestLimpezaBasica(unittest.TestCase):

    def test_remove_assinatura_eletronica(self):
        t = "Decido pela condenacao.\nAssinado eletronicamente por Juiz Fulano"
        r = limpar_texto(t)
        self.assertIn("Decido pela condenacao", r)
        self.assertNotIn("Assinado eletronicamente", r)

    def test_remove_url(self):
        t = "Veja em https://pje.tjba.jus.br/codigo/abc trecho importante"
        r = limpar_texto(t)
        self.assertNotIn("https://", r)
        self.assertIn("trecho importante", r)

    def test_remove_rodape_pje(self):
        t = "Conteudo util\nNum. 12345 - Pág. 1\nMais conteudo"
        r = limpar_texto(t)
        self.assertNotIn("Num. 12345", r)
        self.assertIn("Conteudo util", r)
        self.assertIn("Mais conteudo", r)

    def test_normaliza_quebras_multiplas(self):
        t = "linha1\n\n\n\n\nlinha2"
        r = limpar_texto(t)
        self.assertNotIn("\n\n\n", r)

    def test_string_vazia(self):
        self.assertEqual(limpar_texto(""), "")
        self.assertEqual(limpar_texto(None), "")


class TestRegexNaoGananciosa(unittest.TestCase):
    """Regex com DOTALL/{0,N} devem parar onde esperado, sem engolir texto util."""

    def test_doc_assinado_nao_engole_proxima_peca(self):
        # Padrao "Documento assinado ... Brasilia" deve parar em "Brasilia."
        # e nao engolir o paragrafo seguinte (separado por quebra de linha).
        t = (
            "Documento assinado eletronicamente por Fulano em Brasilia.\n\n"
            "PARTE_UTIL_QUE_DEVE_SOBREVIVER\n\n"
            "## NOVA PECA\nConteudo da nova peca aqui."
        )
        r = limpar_texto(t)
        self.assertIn("PARTE_UTIL", r)
        self.assertIn("NOVA PECA", r)

    def test_autenticidade_documento_nao_engole_tudo(self):
        t = (
            "A autenticidade do documento pode ser verificada no portal X.\n\n"
            "## CONTEUDO_SEGUINTE\n"
            "Trecho que deve sobreviver à limpeza."
        )
        r = limpar_texto(t)
        self.assertIn("CONTEUDO_SEGUINTE", r)
        self.assertIn("sobreviver", r)


class TestVerboseDebugLog(unittest.TestCase):

    def test_debug_log_registra_remocoes(self):
        debug_log = []
        t = "Texto util.\nAssinado eletronicamente por X\nhttps://pje.tjba.jus.br/xpto"
        limpar_texto(t, verbose=True, debug_log=debug_log)
        # Deve ter registrado pelo menos 2 entradas (assinatura + url)
        self.assertGreaterEqual(len(debug_log), 2)
        # Cada entrada tem padrao + trecho
        for entry in debug_log:
            self.assertIn("padrao", entry)
            self.assertIn("trecho", entry)

    def test_debug_log_vazio_quando_nao_ha_lixo(self):
        debug_log = []
        limpar_texto("Texto neutro sem padroes.", verbose=True, debug_log=debug_log)
        self.assertEqual(len(debug_log), 0)


class TestPadroesLixoEstrutura(unittest.TestCase):

    def test_lista_tem_tuplas_nome_padrao(self):
        self.assertGreater(len(PADROES_LIXO), 10)
        for item in PADROES_LIXO:
            self.assertIsInstance(item, tuple)
            self.assertEqual(len(item), 2)
            nome, padrao = item
            self.assertIsInstance(nome, str)
            # Padrao deve ser um re.Pattern compilado
            self.assertTrue(hasattr(padrao, "sub"))


class TestRegressaoCasosCriticos(unittest.TestCase):
    """Garante que conteudo juridico essencial sobrevive a limpeza."""

    def test_preserva_decisao(self):
        t = (
            "## DECISÃO\n"
            "Decido pela procedencia do pedido.\n"
            "Assinado eletronicamente por X\n"
            "Num. 12345 - Pág. 1"
        )
        r = limpar_texto(t)
        self.assertIn("Decido pela procedencia", r)

    def test_preserva_denuncia(self):
        t = (
            "O Ministério Público oferece a presente denúncia em face de JOAO.\n"
            "https://pje.tjba.jus.br/abc\n"
            "Documento assinado eletronicamente em Brasilia."
        )
        r = limpar_texto(t)
        self.assertIn("oferece a presente denúncia", r)
        self.assertIn("JOAO", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
