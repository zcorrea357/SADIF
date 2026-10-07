# Exemplo de uso
from sadif.frameworks_drivers.web.authenticator.basic_auth_strategy import BasicAuthStrategy
from sadif.frameworks_drivers.web.authenticator.bearer_auth_strategy import BearerAuthStrategy
from sadif.frameworks_drivers.web.session_manager import SessionManager

basic_auth_strategy = BasicAuthStrategy(
    "user", "pass"
)  # Assumindo que essa estratégia foi definida anteriormente
bearer_auth_strategy = BearerAuthStrategy(
    "your_token_here"
)  # Assumindo que essa estratégia foi definida anteriormente

session_manager = SessionManager()

# Criar uma sessão com autenticação básica
session_with_basic_auth = session_manager.create_session(basic_auth_strategy)

# Criar uma sessão com autenticação bearer
session_with_bearer_auth = session_manager.create_session(bearer_auth_strategy)
a = session_with_bearer_auth.get("https://httpbin.org/bearer")
print(a.status_code)
# Aqui você pode usar session_with_basic_auth e session_with_bearer_auth para fazer requisições

# Fechar todas as sessões ao final
session_manager.close_all_sessions()
