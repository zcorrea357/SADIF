from sadif.frameworks_drivers.log_manager.sadif_log import LogManager
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)


class UpdateCase:
    """
    A utility class to update case details in TheHive.

    Attributes
    ----------
    session : SessionThehive
        An active session to interact with TheHive's API.

    Methods
    -------
    update_case(case_id: str, update_data: dict):
        Update details of a specific case in TheHive using its ID.

    """

    def __init__(self, session: SessionThehive):
        """
        Initialize the UpdateCase object

        Parameters
        ----------
        session : SessionThehive
            An active session to interact with TheHive's API
        """
        self.session = session
        self.logmanager = LogManager()

    def update_case(self, case_id: str, update_data: dict):
        """
        Update details of a specific case in TheHive using its ID

        Parameters
        ----------
        case_id : str
            The ID of the case to be updated.
        update_data : dict
            A dictionary containing the update data for the case.

        Returns
        -------
        tuple
            The response and status code of the update request.
        """
        path = f"case/{case_id}"
        try:
            response, status_code = self.session.request(
                endpoint=path, method="PATCH", json_data=update_data
            )

            if status_code == 200:
                self.logmanager.log(
                    "info",
                    f"Case {case_id} successfully updated.",
                    category="case_update",
                    task_state="success",
                )
            else:
                self.logmanager.log(
                    "warning",
                    f"Failed to update case {case_id}. Status code: {status_code}",
                    task_state="failed",
                    category="case_update",
                )

            return response, status_code
        except Exception as e:
            self.logmanager.log(
                "error",
                f"Exception occurred while updating case {case_id}: {e}",
                category="case_update_exception",
                task_state="failed",
            )
            self.logmanager.capture_exception(e)
            raise
