from sadif.frameworks_drivers.web.authenticator.bearer_auth_strategy import BearerAuthStrategy
from sadif.frameworks_drivers.web.session_manager import SessionManager

token = "dsa"  # noqa: S105
if __name__ == "__main__":
    bearer_auth_strategy = BearerAuthStrategy(token)

    session_manager = SessionManager()
    authenticated_session = session_manager.create_session(bearer_auth_strategy)
    print(type(authenticated_session))
    response = authenticated_session.get("https://httpbin.org/bearer")
    print(response.status_code)
    print(response.text)

    session_manager.close_all_sessions()
