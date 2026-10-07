import os

# Nunca enviar erros dos testes para o Sentry de produção configurado no variables.json
os.environ.setdefault("SADIF_SENTRYDSN", "")
