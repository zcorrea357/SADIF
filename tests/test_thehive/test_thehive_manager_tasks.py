import unittest
from unittest.mock import Mock

from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_tasks import (
    Task,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)


class TestTask(unittest.TestCase):
    def setUp(self):
        self.mock_session = Mock(spec=SessionThehive)
        self.task = Task(session=self.mock_session)
        self.task_id = "test_task_id"
        self.case_id = "test_case_id"
        self.title = "test_title"

    def test_create_task_in_case(self):
        self.mock_session.request.return_value = "mock_response"
        response = self.task.create_task_in_case(self.case_id, self.title)
        self.mock_session.request.assert_called_once_with(
            f"v1/case/{self.case_id}/task", method="POST", json_data={"title": self.title}
        )
        assert response == "mock_response"

    def test_get_task(self):
        self.mock_session.request.return_value = "mock_response"
        response = self.task.get_task(self.task_id)
        self.mock_session.request.assert_called_once_with(f"v1/task/{self.task_id}", method="GET")
        assert response == "mock_response"

    def test_delete_task(self):
        self.mock_session.request.return_value = "mock_response"
        response = self.task.delete_task(self.task_id)
        self.mock_session.request.assert_called_once_with(
            f"v1/task/{self.task_id}", method="DELETE"
        )
        assert response == "mock_response"

    def test_update_task(self):
        self.mock_session.request.return_value = "mock_response"
        response = self.task.update_task(self.task_id, title="new_title")
        self.mock_session.request.assert_called_once_with(
            f"v1/task/{self.task_id}", method="PATCH", json_data={"title": "new_title"}
        )
        assert response == "mock_response"

    def test_get_task_actions_required(self):
        self.mock_session.request.return_value = "mock_response"
        response = self.task.get_task_actions_required(self.task_id)
        self.mock_session.request.assert_called_once_with(
            f"v1/task/{self.task_id}/actionRequired", method="GET"
        )
        assert response == "mock_response"


if __name__ == "__main__":
    unittest.main()
