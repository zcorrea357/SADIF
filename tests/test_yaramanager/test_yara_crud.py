import unittest

import mongomock

from sadif.frameworks_drivers.sadif_yara.yara_crud import YaraCrud


class TestYaraCrud(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Configuração inicial para todos os testes
        cls.mock_client = mongomock.MongoClient()
        cls.yara_crud = YaraCrud(db_client=cls.mock_client)

    def setUp(self):
        # Configuração antes de cada teste
        self.mock_client.drop_database(
            "test_database"
        )  # Limpar a base de dados antes de cada teste
        self.yara_crud.db = self.mock_client["test_database"]  # Definir uma base de dados de teste

    def test_parse_rule(self):
        # Teste do método parse_rule
        rule_name, content = self.yara_crud.parse_rule("rule ExampleRule")
        self.assertEqual(rule_name, "ExampleRule")
        self.assertEqual(content, "rule ExampleRule")

    @classmethod
    def tearDownClass(cls):
        # Limpeza após todos os testes
        cls.mock_client.close()


if __name__ == "__main__":
    unittest.main()
