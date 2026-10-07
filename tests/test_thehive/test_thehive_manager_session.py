import unittest
from unittest.mock import Mock, patch

import requests

from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)


class TestSessionTheHive(unittest.TestCase):
    def setUp(self):
        self.session = SessionThehive()

    def test_init(self):
        assert self.session.base_url == "http://localhost:9000/api/"
        assert self.session.headers == {}
        assert self.session.cookies == {}
        assert self.session.auth is None

    def test_reset_auth(self):
        self.session.headers["Authorization"] = "Bearer some_token"
        self.session.cookies["THEHIVE-SESSION"] = "some_session"
        self.session.auth = "basic_auth"

        self.session._reset_auth()

        assert "Authorization" not in self.session.headers
        assert "THEHIVE-SESSION" not in self.session.cookies
        assert self.session.auth is None

    def test_set_api_key(self):
        api_key = "some_key"
        self.session.set_api_key(api_key)
        assert self.session.headers["Authorization"] == f"Bearer {api_key}"

    def test_set_basic_auth(self):
        with patch("requests.auth.HTTPBasicAuth", autospec=True) as mock_auth:
            login = "user"
            padssdword = "dsa"
            self.session.set_basic_auth(login, padssdword)
            mock_auth.assert_called_once_with(login, padssdword)
            assert self.session.auth == mock_auth.return_value

    def test_set_session(self):
        session_id = "some_session"
        self.session.set_session(session_id)
        assert self.session.cookies["THEHIVE-SESSION"] == session_id

    def test_set_organisation(self):
        org_name = "some_org"
        self.session.set_organisation(org_name)
        assert self.session.headers["X-Organisation"] == org_name

    @patch(
        "sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session.requests.request"
    )
    def test_request_success_json(self, mock_request):
        endpoint = "some_endpoint"
        method = "GET"
        json_data = {"key": "value"}
        response_mock = Mock()
        response_mock.raise_for_status.return_value = None
        response_mock.json.return_value = json_data
        response_mock.status_code = 200
        mock_request.return_value = response_mock

        response, status_code = self.session.request(endpoint, method, json_data)

        assert response == json_data
        assert status_code == 200

    @patch(
        "sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session.requests.request"
    )
    def test_request_http_error_returns_body_and_status(self, mock_request):
        response_mock = Mock()
        response_mock.ok = False
        response_mock.status_code = 404
        response_mock.json.return_value = {"type": "NotFoundError"}
        mock_request.return_value = response_mock

        response, status_code = self.session.request("v1/case/~1")

        assert response == {"type": "NotFoundError"}
        assert status_code == 404

    @patch(
        "sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session.requests.request"
    )
    def test_request_connection_error_returns_status_zero(self, mock_request):
        mock_request.side_effect = requests.ConnectionError("connection refused")

        response, status_code = self.session.request("status")

        assert response == "connection refused"
        assert status_code == 0


if __name__ == "__main__":
    unittest.main()
