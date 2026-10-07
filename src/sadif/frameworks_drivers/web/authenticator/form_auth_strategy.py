from requests import Session

from sadif.interfaces.web.authenticator import AuthStrategy


class FormAuthStrategy(AuthStrategy):
    """Authenticates by POSTing credentials to a login endpoint and keeping the session cookies."""

    def __init__(self, login_url: str, form_data: dict[str, str]) -> None:
        self.login_url = login_url
        self.form_data = form_data

    def authenticate(self, session: Session) -> Session:
        response = session.post(self.login_url, data=self.form_data, allow_redirects=True)
        response.raise_for_status()
        return session
