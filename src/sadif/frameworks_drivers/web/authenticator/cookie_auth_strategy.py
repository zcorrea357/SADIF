from requests import Session

from sadif.interfaces.web.authenticator import AuthStrategy


class CookieAuthStrategy(AuthStrategy):
    """Authenticates by setting one or more cookies on the session."""

    def __init__(self, cookies: dict[str, str]) -> None:
        self.cookies = cookies

    def authenticate(self, session: Session) -> Session:
        for name, value in self.cookies.items():
            session.cookies.set(name, value)
        return session
