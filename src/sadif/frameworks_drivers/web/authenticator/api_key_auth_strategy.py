from requests import Session

from sadif.interfaces.web.authenticator import AuthStrategy


class ApiKeyAuthStrategy(AuthStrategy):
    """Authenticates by injecting an API key as a header or query parameter."""

    def __init__(self, key: str, value: str, location: str = "header") -> None:
        self.key = key
        self.value = value
        self.location = location.lower()

    def authenticate(self, session: Session) -> Session:
        if self.location == "query":
            session.params = {**(session.params or {}), self.key: self.value}  # type: ignore[assignment]
        else:
            session.headers[self.key] = self.value
        return session
