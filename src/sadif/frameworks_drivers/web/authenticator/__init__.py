# Classe que utiliza uma estratégia de autenticação
from requests import Session

from sadif.interfaces.web.authenticator import AuthStrategy


class Authenticator(AuthStrategy):
    """
    Context wrapper that delegates authentication to a concrete AuthStrategy.

    It is itself an AuthStrategy, so it can be passed directly to
    SessionManager.create_session.
    """

    def __init__(self, strategy: AuthStrategy) -> None:
        self.strategy = strategy

    def authenticate(self, session: Session) -> Session:
        return self.strategy.authenticate(session)
