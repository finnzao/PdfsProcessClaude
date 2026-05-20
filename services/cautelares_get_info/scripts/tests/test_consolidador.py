"""Testes do consolidador."""

import json
import tempfile
import unittest
from pathlib import Path

from services.cautelares_get_info.scripts.consolidar import (
    carregar_jsons,
    flatten_dict,
)


class TestFlattenDict(unittest.TestCase):
    def test_dict_simples(self):
        r = flatten_dict({"a": 1, "b": "x"})
        self.assertEqual(r, {"a": 1, "b": "x"})

    def test_dict_aninhado(self):
        r = flatten_dict({"a": {"b": 1, "c": 2}, "d": 3})
        self.assertEqual(r, {"a.b": 1, "a.c": 2, "d": 3})

    def test_dict_com_lista(self):
        r = flatten_dict({"itens": ["x", "y", "z"]})
        self.assertEqual(r, {"itens": "x; y; z"})

    def test_dict_profundamente_aninhado(self):
        r = flatten_dict({"a": {"b": {"c": "valor"}}})
        self.assertEqual(r, {"a.b.c": "valor"})


class TestCarregarJsons(unittest.TestCase):
    def test_diretorio_inexistente(self):
        self.assertEqual(carregar_jsons(Path("/diretorio/que/nao/existe")), [])

    def test_carregar_lista_de_dicts(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.json").write_text(json.dumps([{"n": 1}, {"n": 2}]))
            (p / "b.json").write_text(json.dumps([{"n": 3}]))
            r = carregar_jsons(p)
            self.assertEqual(len(r), 3)

    def test_carregar_dict_individual(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "x.json").write_text(json.dumps({"chave": "valor"}))
            r = carregar_jsons(p)
            self.assertEqual(r, [{"chave": "valor"}])

    def test_ignora_json_invalido(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "ok.json").write_text(json.dumps({"a": 1}))
            (p / "ruim.json").write_text("{ nao e json valido")
            r = carregar_jsons(p)
            self.assertEqual(r, [{"a": 1}])


if __name__ == "__main__":
    unittest.main()
