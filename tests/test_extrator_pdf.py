"""
tests/test_extrator_pdf.py — Funcoes auxiliares do pipeline.

Cobre:
  - deve_ocrizar: detecta texto curto, encoding corrompido, palavras reais
  - _eh_capa_pje: identifica capa por score
  - _deve_agrupar: gaps, doc_id como separador, datas disjuntas
  - _e_continuacao: mesmo doc_id + tipo + contigiidade
  - _md_hash: estabilidade
  - HEURISTICAS_CAPA_VERSAO: versionamento
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from common.extrator_pdf import (
    HEURISTICAS_CAPA_VERSAO,
    _deve_agrupar,
    _e_continuacao,
    _eh_capa_pje,
    _md_hash,
    deve_ocrizar,
)


class TestDeveOcrizar(unittest.TestCase):

    def test_texto_curto_aciona_ocr(self):
        precisa, motivo = deve_ocrizar("oi")
        self.assertTrue(precisa)
        self.assertIn("curto", motivo.lower())

    def test_texto_vazio_aciona_ocr(self):
        precisa, _ = deve_ocrizar("")
        self.assertTrue(precisa)

    def test_texto_real_nao_aciona(self):
        t = (
            "O Ministério Público do Estado da Bahia oferece a presente denúncia "
            "em face de João da Silva Santos, brasileiro, solteiro, residente em "
            "Rio Real, como incurso nas sanções do artigo 157, parágrafo segundo, "
            "do Código Penal, pois conforme apurado em sede de inquérito policial, "
            "o denunciado praticou roubo majorado contra a vítima Maria Oliveira, "
            "tendo subtraído valores e ameaçado de morte. Os fatos ocorreram em "
            "horário noturno, na zona urbana do município. Diversas testemunhas "
            "presenciaram a abordagem e prestaram depoimentos coerentes."
        )
        precisa, motivo = deve_ocrizar(t)
        self.assertFalse(precisa, msg=f"Aceitar texto longo: motivo={motivo}")

    def test_encoding_corrompido_aciona(self):
        # Muitos caracteres invalidos -> deve forcar OCR
        t = "∞∞∞ÈÁ„‡ï " * 50 + " texto"
        precisa, motivo = deve_ocrizar(t)
        self.assertTrue(precisa)


class TestEhCapaPje(unittest.TestCase):

    def test_capa_completa(self):
        texto_capa = (
            "PJe - Processo Judicial Eletrônico\n"
            "Órgão julgador: Vara Criminal de Rio Real\n"
            "Classe: Ação Penal\n"
            "Valor da causa: R$ 0,00\n"
            "Documentos\nTipo\nNum.\n"
        )
        eh_capa, zona_cinza, score = _eh_capa_pje(texto_capa)
        self.assertTrue(eh_capa)
        self.assertGreaterEqual(score, 5)

    def test_texto_neutro_nao_e_capa(self):
        t = "Texto qualquer sem nenhum metadado do PJe. Apenas conteudo livre."
        eh_capa, _, score = _eh_capa_pje(t)
        self.assertFalse(eh_capa)

    def test_capa_parcial_zona_cinza(self):
        # 1 ou 2 hits = abaixo de zona cinza, nao e capa
        t = "PJe - Processo Judicial Eletrônico\nAlgum conteudo."
        eh_capa, zona_cinza, score = _eh_capa_pje(t)
        self.assertFalse(eh_capa)


class TestDeveAgrupar(unittest.TestCase):

    def _peca(self, tipo, pag_ini, pag_fim, texto="", doc_ids=None, doc_id=None):
        return {
            "tipo": tipo,
            "pag_ini": pag_ini,
            "pag_fim": pag_fim,
            "pag": pag_ini,
            "texto": texto,
            "doc_ids": doc_ids or [],
            "doc_id": doc_id,
        }

    def test_mesmo_tipo_contiguo_agrupa(self):
        u = self._peca("DENÚNCIA", 3, 4, texto="Denúncia parte 1")
        a = self._peca("DENÚNCIA", 5, 5, texto="Denúncia parte 2")
        self.assertTrue(_deve_agrupar(u, a))

    def test_gap_grande_nao_agrupa(self):
        u = self._peca("DENÚNCIA", 3, 4)
        a = self._peca("DENÚNCIA", 10, 11)  # gap=6
        self.assertFalse(_deve_agrupar(u, a))

    def test_doc_ids_distintos_separa(self):
        u = self._peca("DECISÃO", 5, 5, doc_ids=[("11111", "1")])
        a = self._peca("DECISÃO", 6, 6, doc_id=("99999", "1"))
        self.assertFalse(_deve_agrupar(u, a))

    def test_mesmo_doc_id_agrupa(self):
        u = self._peca("DECISÃO", 5, 5, doc_ids=[("11111", "1")])
        a = self._peca("DECISÃO", 6, 6, doc_id=("11111", "2"))
        self.assertTrue(_deve_agrupar(u, a))

    def test_datas_disjuntas_mesmo_tipo_nao_agrupa(self):
        u = self._peca("DECISÃO", 5, 5, texto="Em 01/01/2024 decido...")
        a = self._peca("DECISÃO", 6, 6, texto="Em 15/06/2025 decido...")
        self.assertFalse(_deve_agrupar(u, a))

    def test_doc_orfao_apos_peca_completa(self):
        u = self._peca("DENÚNCIA", 5, 7)
        a = self._peca("DOC", 8, 8)
        self.assertTrue(_deve_agrupar(u, a))

    def test_doc_orfao_com_gap_grande_nao_agrupa(self):
        u = self._peca("DENÚNCIA", 5, 7)
        a = self._peca("DOC", 15, 15)
        self.assertFalse(_deve_agrupar(u, a))


class TestEContinuacao(unittest.TestCase):

    def test_continuacao_mesmo_doc_id(self):
        ant = {"tipo": "DENÚNCIA", "pag_fim": 5, "doc_ids": [("12345", "1")]}
        atual = {"tipo": "DENÚNCIA", "pag": 6, "doc_id": ("12345", "2")}
        self.assertTrue(_e_continuacao(ant, atual))

    def test_nao_continuacao_tipos_diferentes(self):
        ant = {"tipo": "DENÚNCIA", "pag_fim": 5, "doc_ids": [("12345", "1")]}
        atual = {"tipo": "DECISÃO", "pag": 6, "doc_id": ("12345", "2")}
        self.assertFalse(_e_continuacao(ant, atual))

    def test_nao_continuacao_gap_grande(self):
        ant = {"tipo": "DENÚNCIA", "pag_fim": 5, "doc_ids": [("12345", "1")]}
        atual = {"tipo": "DENÚNCIA", "pag": 10, "doc_id": ("12345", "2")}
        self.assertFalse(_e_continuacao(ant, atual))

    def test_nao_continuacao_sem_doc_id_compativel(self):
        ant = {"tipo": "DENÚNCIA", "pag_fim": 5, "doc_ids": [("12345", "1")]}
        atual = {"tipo": "DENÚNCIA", "pag": 6, "doc_id": ("99999", "1")}
        self.assertFalse(_e_continuacao(ant, atual))


class TestMdHash(unittest.TestCase):

    def test_estabilidade(self):
        t = "Conteudo de teste"
        h1 = _md_hash(t)
        h2 = _md_hash(t)
        self.assertEqual(h1, h2)

    def test_diferente_para_textos_diferentes(self):
        h1 = _md_hash("a")
        h2 = _md_hash("b")
        self.assertNotEqual(h1, h2)

    def test_hash_string_vazia(self):
        h = _md_hash("")
        self.assertTrue(h)
        self.assertEqual(len(h), 32)


class TestVersionamentoHeuristicas(unittest.TestCase):

    def test_versao_definida(self):
        self.assertTrue(HEURISTICAS_CAPA_VERSAO)
        self.assertIsInstance(HEURISTICAS_CAPA_VERSAO, str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
