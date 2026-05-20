"""
tests/test_classificador.py — Janela deslizante, voto multi-janela e confianca.

Cobre:
  - Classificacao de tipos criticos em texto curto e longo
  - Voto multi-janela (inicio + meio + fim)
  - Confianca calculada por margem
  - Fallback quando nenhum tipo atinge minimo
  - Regressao: tipos sensiveis (DENUNCIA, SENTENCA, AUDIENCIA_CUSTODIA,
    CUMPRIMENTO_SURSIS vs EXTINCAO_PUNIBILIDADE)
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from common.classificador_pecas import (
    classificar_peca,
    classificar_peca_com_score,
    PECAS_COMPLETAS,
    PECAS_RESUMO,
    PECAS_DESCARTE,
)


class TestTiposCriticos(unittest.TestCase):

    def test_denuncia_basica(self):
        t = "O MINISTÉRIO PÚBLICO oferece a presente denúncia em face de JOÃO DA SILVA, denuncia como incurso nas sanções do art. 157 do CP."
        tipo = classificar_peca(t)
        self.assertEqual(tipo, "DENÚNCIA")

    def test_sentenca_julgo_procedente(self):
        t = "SENTENÇA\n\nVistos. Decido. Julgo procedente o pedido e condeno o réu nas penas do art. 157 do CP."
        tipo = classificar_peca(t)
        self.assertEqual(tipo, "SENTENÇA")

    def test_audiencia_custodia(self):
        t = "ATA de audiência de custódia. Realizada nos termos do art. 310 do CPP. Homologação do flagrante."
        tipo = classificar_peca(t)
        self.assertEqual(tipo, "AUDIENCIA_CUSTODIA")

    def test_liberdade_provisoria(self):
        t = "DECISÃO\n\nDefiro a liberdade provisória ao conduzido, nos termos do art. 321 do CPP."
        tipo = classificar_peca(t)
        self.assertEqual(tipo, "LIBERDADE_PROVISORIA")

    def test_preventiva(self):
        t = "Decisão. Decreto a prisão preventiva do indiciado, com base no art. 312 do CPP."
        tipo = classificar_peca(t)
        self.assertEqual(tipo, "PREVENTIVA")

    def test_bo(self):
        t = "BOLETIM DE OCORRÊNCIA\nRelato/Histórico do fato narrado pela vítima. Dados do registro."
        tipo = classificar_peca(t)
        self.assertEqual(tipo, "BO")

    def test_doc_indefinido(self):
        """Texto sem sinais retorna DOC."""
        t = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nada juridico aqui."
        tipo = classificar_peca(t)
        self.assertEqual(tipo, "DOC")


class TestRegressaoCumprimentoVsExtincao(unittest.TestCase):
    """
    CUMPRIMENTO_SURSIS tem peso 20 e minimo 15, devendo vencer
    EXTINCAO_PUNIBILIDADE quando ambos os sinais aparecem (sentenca extingue
    PORQUE foi cumprido o periodo de prova).
    """

    def test_cumprimento_sursis_vence(self):
        t = (
            "Cumprido o período de prova nos termos do art. 89, §5º, da Lei 9.099/95, "
            "declaro extinta a punibilidade."
        )
        tipo = classificar_peca(t)
        self.assertEqual(tipo, "CUMPRIMENTO_SURSIS")

    def test_extincao_pura_sem_cumprimento(self):
        t = "Declaro extinta a punibilidade pela prescrição (art. 107 do CP)."
        tipo = classificar_peca(t)
        self.assertEqual(tipo, "EXTINCAO_PUNIBILIDADE")

    def test_cumprimento_anpp_vence(self):
        t = "Cumpridas as condições do ANPP nos termos do art. 28-A, §13, do CPP."
        tipo = classificar_peca(t)
        self.assertEqual(tipo, "CUMPRIMENTO_ANPP")


class TestRetornoTriplo(unittest.TestCase):

    def test_classificar_peca_com_score_retorna_3(self):
        t = "Oferece a presente denúncia"
        r = classificar_peca_com_score(t)
        self.assertEqual(len(r), 3)
        tipo, score, conf = r
        self.assertEqual(tipo, "DENÚNCIA")
        self.assertGreater(score, 0)
        self.assertGreaterEqual(conf, 0.0)
        self.assertLessEqual(conf, 1.0)

    def test_doc_score_zero(self):
        tipo, score, conf = classificar_peca_com_score("")
        self.assertEqual(tipo, "DOC")
        self.assertEqual(score, 0)


class TestConfianca(unittest.TestCase):

    def test_confianca_alta_em_caso_obvio(self):
        t = "OFEREÇO A PRESENTE DENÚNCIA. Denuncia como incurso. Ministério Público oferece."
        _, score, conf = classificar_peca_com_score(t)
        # Confianca alta quando ha forte margem
        self.assertGreater(conf, 0.5)

    def test_confianca_zero_quando_sem_match(self):
        _, _, conf = classificar_peca_com_score("texto totalmente neutro sem sinais")
        self.assertEqual(conf, 0.0)


class TestVotoMultiJanela(unittest.TestCase):
    """Para textos longos, o voto agregado entre janelas deve manter a classificacao."""

    def test_texto_longo_com_sinais_no_inicio(self):
        # Texto longo com sinais de DENUNCIA no inicio + bastante ruido depois
        inicio = "O MINISTÉRIO PÚBLICO oferece a presente denúncia contra Fulano. Denuncia como incurso art. 157."
        ruido = "Texto irrelevante de preenchimento sem sinais juridicos especificos. " * 200
        t = inicio + "\n\n" + ruido
        self.assertGreater(len(t), 3000)  # garante que e longo
        tipo = classificar_peca(t)
        self.assertEqual(tipo, "DENÚNCIA")

    def test_voto_agregado_nao_quebra_curto(self):
        # Texto curto: voto agregado nao se aplica
        t = "Sentença. Julgo procedente."
        tipo = classificar_peca(t)
        self.assertEqual(tipo, "SENTENÇA")

    def test_multi_janela_desativavel(self):
        # Quando multi_janela=False, deve funcionar com a primeira janela apenas
        t = "OFEREÇO A PRESENTE DENÚNCIA contra Fulano."
        tipo, score, _ = classificar_peca_com_score(t, multi_janela=False)
        self.assertEqual(tipo, "DENÚNCIA")
        self.assertGreater(score, 0)


class TestCategoriasConjuntos(unittest.TestCase):

    def test_pecas_completas_contem_denuncia(self):
        self.assertIn("DENÚNCIA", PECAS_COMPLETAS)
        self.assertIn("SENTENÇA", PECAS_COMPLETAS)
        self.assertIn("AUDIENCIA_CUSTODIA", PECAS_COMPLETAS)

    def test_pecas_resumo_contem_oficio(self):
        self.assertIn("OFÍCIO", PECAS_RESUMO)
        self.assertIn("CERTIDÃO", PECAS_RESUMO)

    def test_pecas_descarte_contem_assinatura(self):
        self.assertIn("ASSINATURA", PECAS_DESCARTE)

    def test_categorias_nao_se_sobrepoem(self):
        intersecao = (PECAS_COMPLETAS & PECAS_RESUMO) | \
                     (PECAS_COMPLETAS & PECAS_DESCARTE) | \
                     (PECAS_RESUMO & PECAS_DESCARTE)
        self.assertEqual(intersecao, set())


class TestScoreMinimoFiltragem(unittest.TestCase):
    """Score minimo pode rebaixar peca para DOC se nao bate threshold."""

    def test_score_minimo_filtra(self):
        t = "Apelação"  # sinal fraco (peso 1) sem contexto
        # Sem score minimo, classifica
        tipo_sem, _, _ = classificar_peca_com_score(t, score_minimo_para_aceitar=0)
        # Com score minimo alto, deveria virar DOC
        tipo_com, _, _ = classificar_peca_com_score(t, score_minimo_para_aceitar=100)
        self.assertEqual(tipo_com, "DOC")


if __name__ == "__main__":
    unittest.main(verbosity=2)
