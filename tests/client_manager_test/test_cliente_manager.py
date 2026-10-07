import unittest

from mongomock import MongoClient as MockMongoClient

from sadif.clientmanager.client_data_manager import ClientManager


class TestClientManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initial setup for all tests
        cls.mock_client = MockMongoClient()
        cls.client_manager = ClientManager(db_client=cls.mock_client)

    def test_update_module_info_not_allowed_module(self):
        """Test updating module info with a module name that is not allowed."""
        result = self.client_manager.update_module_info(
            "TestClient", "NotAllowedModule", {"info": "test"}
        )
        self.assertIn("Erro: Módulo 'NotAllowedModule' não é permitido.", result)

    def test_update_module_info_allowed_module(self):
        """Test updating module info with a module listed in CLIENTS_MODULES."""
        collection_name = self.client_manager._generate_collection_name("AllowedClient")
        self.client_manager.db[collection_name].insert_one(
            {"client_name": "AllowedClient", "company": "Company", "ciid": "CIID-1", "Modules": {}}
        )
        result = self.client_manager.update_module_info(
            "AllowedClient", "ModuloA", {"info": "test"}
        )
        self.assertEqual("Informações do módulo 'ModuloA' atualizadas com sucesso.", result)
        self.assertEqual(
            {"ModuloA": {"info": "test"}}, self.client_manager.find_client_modules("AllowedClient")
        )

    # Add more tests for other methods...


if __name__ == "__main__":
    unittest.main()
