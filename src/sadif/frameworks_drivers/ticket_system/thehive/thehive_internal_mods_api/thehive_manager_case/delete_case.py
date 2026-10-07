from sadif.frameworks_drivers.log_manager.sadif_log import LogManager
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)


class DeleteCase:
    """
    A utility class to handle the deletion of a case in TheHive.

    Attributes
    ----------
    session : SessionThehive
        An active session to interact with TheHive's API.

    Methods
    -------
    delete_case(id_or_name: str):
        Delete a case from TheHive using its ID or name.

    """

    def __init__(self, session: SessionThehive):
        """
        Initialize the DeleteCase object

        Parameters
        ----------
        session : SessionThehive
            An active session to interact with TheHive's API.
        """
        self.session = session
        self.logmanager = LogManager()

    def delete_case(self, idcase: str):
        """
        Delete a specific case in TheHive using either its ID or name.

        Parameters
        ----------
        idcase : str
            The ID or name of the case to be deleted.

        Returns
        -------
        tuple
            The response and status code of the delete request.
        """
        try:
            path = f"v1/case/{idcase}"
            response, status_code = self.session.request(endpoint=path, method="DELETE")
            if 200 <= status_code < 300:
                self.logmanager.log(
                    "info",
                    f"Case {idcase} successfully deleted.",
                    category="case_deletion",
                    task_state="success",
                )
            else:
                self.logmanager.log(
                    "warning",
                    f"Failed to delete case {idcase}. Status code: {status_code}",
                    category="case_deletion",
                    task_state="failed",
                )
            return response, status_code
        except Exception as e:
            self.logmanager.capture_exception(e, f"Error occurred while deleting case {idcase}")
            self.logmanager.log(
                "error",
                f"Error deleting case {idcase}: {e}",
                category="case_deletion",
                task_state="failed",
            )
            raise
