from pymongo import MongoClient

from sadif.config.soar_config import SadifConfiguration
from sadif.frameworks_drivers.modules_manager import ModuleDatabaseManager

# Exemplo de uso
if __name__ == "__main__":
    config = SadifConfiguration()
    db_url = config.get_configuration("MONGODB_URL")
    db_real = MongoClient(db_url)
    # Criação de um módulo específico com seu esquema
    db_manager = ModuleDatabaseManager(db_real)
    # Criação de uma coleção para o módulo "Cursos" com validação de esquema
    validation_schema = {
        "bsonType": "object",
        "required": ["nome", "descricao"],
        "properties": {
            "nome": {"bsonType": "string", "description": "deve ser uma string e é obrigatório"},
            "descricao": {
                "bsonType": "string",
                "description": "deve ser uma string e é obrigatório",
            },
        },
    }
    db_manager.create_module_collection("Cursos", validation_schema)

    # Inserção de documentos na coleção "Cursos"
    curso_python = {
        "nome": "Python para Iniciantes",
        "descricao": "Curso introdutório sobre Python.",
    }
    curso_java = {
        "nome": "Java Avançado",
        "descricao": "Curso avançado de Java para desenvolvedores experientes.",
    }

    # Remove os cursos de uma execução anterior (o campo "nome" tem índice único)
    for curso in (curso_python, curso_java):
        db_manager.delete_document("Cursos", {"nome": curso["nome"]})

    db_manager.insert_document("Cursos", curso_python)
    db_manager.insert_document("Cursos", curso_java)

    # Busca de documentos na coleção "Cursos"
    print("Buscando cursos com 'Python' no nome:")
    cursos_python = db_manager.find_documents("Cursos", {"nome": {"$regex": "Python"}})
    for curso in cursos_python:
        print(curso)

    # Atualização de um documento na coleção "Cursos"
    db_manager.update_document(
        "Cursos",
        {"nome": "Python para Iniciantes"},
        {"descricao": "Curso completo de Python para iniciantes."},
    )

    # Deleção de um documento na coleção "Cursos"
    # db_manager.delete_document("Cursos", {"nome": "Java Avançado"})

    # Listagem de todos os documentos na coleção "Cursos"
    print("\nListagem de todos os cursos:")
    todos_cursos = db_manager.list_module_data("Cursos")
    for curso in todos_cursos:
        print(curso)
