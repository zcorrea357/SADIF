from requests.exceptions import RequestException

from sadif.frameworks_drivers.log_manager.sadif_log import LogManager
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)


class ListCase:
    """
    A utility class to retrieve a list of cases from TheHive.

    Attributes
    ----------
    session : SessionThehive
        An active session to interact with TheHive's API.

    Methods
    -------
    list_cases():
        Fetch a list of cases from TheHive

    """

    def __init__(self, session: SessionThehive):
        """
        Initialize the ListCase object.

        Parameters
        ----------
        session : SessionThehive
            An active session to interact with TheHive's API.
        """
        self.session = session
        self.logmanager = LogManager()

    def list_cases(self):
        """
        Retrieve a list of cases from TheHive.

        Returns
        -------
        tuple
            A tuple containing the response and status of the list request. If there's
            a request exception, returns None for the response and the error message
            as the status.
        """
        endpoint = "case"
        try:
            response, status = self.session.request(endpoint=endpoint)

            if status == 200:
                self.logmanager.log(
                    "info",
                    "Successfully retrieved the list of cases.",
                    category="case_list",
                    task_state="success",
                )
            else:
                self.logmanager.log(
                    "warning",
                    f"Failed to retrieve cases. Status code: {status}",
                    category="case_list",
                    task_state="failed",
                )

            return response, status
        except RequestException as e:
            self.logmanager.log(
                "error",
                f"RequestException encountered: {e!s}",
                category="case_list_exception",
                task_state="failed",
            )
            self.logmanager.capture_exception(e)
            return None, f"Error in request: {e!s}"
