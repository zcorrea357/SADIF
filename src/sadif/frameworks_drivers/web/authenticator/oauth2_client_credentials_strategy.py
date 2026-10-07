from requests import Session

from sadif.interfaces.web.authenticator import AuthStrategy


class OAuth2ClientCredentialsStrategy(AuthStrategy):
    """Authenticates via the OAuth 2.0 Client Credentials grant (RFC 6749 §4.4)."""

    def __init__(self, token_url: str, client_id: str, client_secret: str, scope: str = "") -> None:
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope

    def authenticate(self, session: Session) -> Session:
        payload: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if self.scope:
            payload["scope"] = self.scope
        response = session.post(self.token_url, data=payload)
        response.raise_for_status()
        token = response.json()["access_token"]
        session.headers["Authorization"] = f"Bearer {token}"
        return session
