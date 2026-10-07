from sadif.frameworks_drivers.log_manager.sadif_log import LogManager
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)


class GetCase:
    """
    A utility class to retrieve case details from TheHive.

    Attributes
    ----------
    session : SessionThehive
        An active session to interact with TheHive's API

    Methods
    -------
    fetch_case(id_or_name: str):
        Fetch details of a specific case from TheHive using its ID or name.

    """

    def __init__(self, session: SessionThehive):
        """
        Initialize the GetCase object.

        Parameters
        ----------
        session : SessionThehive
            An active session to interact with TheHive's API.
        """
        self.session = session
        self.logmanager = LogManager()

    def fetch_case(self, id_or_name: str):
        """
        Retrieve details of a specific case in TheHive using either its ID or name.

        Parameters
        ----------
        id_or_name : str
            The ID or name of the case to be fetched.

        Returns
        -------
        tuple
            The response and status code of the fetch request.
        """
        try:
            path = f"v1/case/{id_or_name}"
            response, status_code = self.session.request(endpoint=path)

            if status_code == 200:
                self.logmanager.log(
                    "info",
                    f"Successfully fetched case details for {id_or_name}.",
                    category="case_fetch",
                    task_state="success",
                )
            else:
                self.logmanager.log(
                    "warning",
                    f"Case {id_or_name} not found or could not be fetched. Status code: {status_code}",
                    category="case_fetch",
                    task_state="failed",
                )

            return response, status_code
        except Exception as e:
            self.logmanager.capture_exception(e, f"Error occurred while fetching case {id_or_name}")
            self.logmanager.log(
                "error",
                f"Exception during fetching case {id_or_name}: {e}",
                category="case_fetch_exception",
            )
