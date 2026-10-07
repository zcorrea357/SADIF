from pathlib import Path

from sadif.config.soar_config import SadifConfiguration

# Carrega configurações a partir de um arquivo JSON externo (em vez do variables.json padrão)
config_file = Path(__file__).parent / "externodefault_config.json"
config_instance = SadifConfiguration(config_file=str(config_file))

if __name__ == "__main__":
    print("mongodb_url:", config_instance.get_configuration("mongodb_url"))
    print("sentry:", config_instance.get_configuration("sentry"))
