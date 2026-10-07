import unittest
from unittest.mock import Mock

from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_comment import (
    CaseComment,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)


class TestCaseComment(unittest.TestCase):
    def setUp(self):
        self.session = Mock(spec=SessionThehive)
        self.case_comment = CaseComment(session=self.session)

    def test_create_for_case(self):
        self.session.request.return_value = (
            "response",
            200,
        )  # Mock the return value of session.request
        response, status_code = self.case_comment.create_for_case("case_id", "message")
        self.session.request.assert_called_once_with(
            "v1/case/case_id/comment", method="POST", json_data={"message": "message"}
        )
        assert response == "response"
        assert status_code == 200

    def test_create_for_alert(self):
        self.session.request.return_value = ("response", 200)
        response, status_code = self.case_comment.create_for_alert("alert_id", "message")
        self.session.request.assert_called_once_with(
            "v1/alert/alert_id/comment", method="POST", json_data={"message": "message"}
        )
        assert response == "response"
        assert status_code == 200

    def test_delete(self):
        self.session.request.return_value = ("response", 200)
        response, status_code = self.case_comment.delete("comment_id")
        self.session.request.assert_called_once_with("v1/comment/comment_id", method="DELETE")
        assert response == "response"
        assert status_code == 200

    def test_update(self):
        self.session.request.return_value = ("response", 200)
        response, status_code = self.case_comment.update("comment_id", "new_message")
        self.session.request.assert_called_once_with(
            "v1/comment/comment_id", method="PATCH", json_data={"message": "new_message"}
        )
        assert response == "response"
        assert status_code == 200


if __name__ == "__main__":
    unittest.main()
