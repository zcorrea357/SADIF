from sadif.config.sadif_config import SadifConfiguration

if __name__ == "__main__":
    config = SadifConfiguration()
    thehive_url = config.get_configuration("THEHIVE")
    thehive_api_key = config.get_configuration("THEHIVE_API_SERVICE")
    mongodb_url = config.get_configuration("MONGODB_URL")
    sentry_dsn = config.get_configuration("SENTRYDSN")

    # Imprimir as configurações
    print(f"TheHive URL: {thehive_url}")
    print(f"TheHive API Key: {thehive_api_key}")
    print(f"MongoDB URL: {mongodb_url}")
    print(f"Sentry DSN: {sentry_dsn}")
