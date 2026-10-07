from sadif.frameworks_drivers.log_manager.sadif_log import LogManager
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_datatype import (
    CaseDataType,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)


class CreateCase:
    def __init__(self, session: SessionThehive):
        """
        Initialize the CreateCase object.

        Parameters
        ----------
        session : SessionThehive
            An active session to interact with TheHive's API.

        Raises
        ------
        ValueError
            If the session is not an instance of SessionThehive.
        """
        if not isinstance(session, SessionThehive):
            msg = "session should be an instance of SessionThehive"
            raise ValueError(msg)
        self.session = session
        self.logmanager = LogManager()

    def _check_case_exist(self, title: str) -> bool:
        """
        Check if a case with the given title already exists in the system.

        Parameters
        ----------
        title : str
            Title of the case to be checked.

        Returns
        -------
        bool
            True if the case exists, False otherwise.
        """
        # GET "case" (API v0) devolve só a primeira página (10 casos), então casos
        # antigos com o mesmo título passariam despercebidos: filtra pelo título na API v1.
        query = {
            "query": [
                {"_name": "listCase"},
                {"_name": "filter", "_eq": {"_field": "title", "_value": title}},
            ]
        }
        response, _ = self.session.request("v1/query", method="POST", json_data=query)
        if not isinstance(response, list):
            self.logmanager.log(
                "warning",
                f"Could not check if a case titled {title!r} exists: {response}",
                category="case_creation",
                task_state="failed",
            )
            return False
        return any(isinstance(case, dict) and case.get("title") == title for case in response)

    def _validate_inputs(self, case_data: CaseDataType):
        """
        Validate the input data for creating a case.

        Parameters
        ----------
        case_data : CaseDataType
            Data to be validated for case creation.

        Raises
        ------
        ValueError
            If any validation check fails.
        """

        self._validate_string_length(case_data.title, 1, 512, "title")
        self._validate_string_length(case_data.description, 0, 1048576, "description")
        self._validate_in_list(case_data.severity, [1, 2, 3, 4], "severity")
        # POST /api/case (API v0) aceita só TLP 0-3 (White, Green, Amber, Red): 4 dá 400
        self._validate_in_list(case_data.tlp, [0, 1, 2, 3], "tlp")
        self._validate_in_list(case_data.pap, [0, 1, 2, 3], "pap")
        self._validate_string_length(case_data.status, 1, 64, "status")

    def _validate_string_length(self, string: str, min_len: int, max_len: int, name: str):
        """
        Validate the length of a string against minimum and maximum allowed values.

        Parameters
        ----------
        string : str
            The string to be validated.
        min_len : int
            The minimum allowed length for the string.
        max_len : int
            The maximum allowed length for the string.
        name : str
            The name of the field for which the string is being validated.

        Raises
        ------
        ValueError
            If the string's length is not within the specified bounds.
        """
        if not min_len <= len(string) <= max_len:
            msg = f"{name} length should be between {min_len} and {max_len} characters, got {len(string)}"
            raise ValueError(msg)

    def _validate_in_list(self, value, valid_list, name):
        """
        Validate that a value is within a specified list.

        Parameters
        ----------
        value : any
            The value to be validated.
        valid_list : list
            A list of valid values.
        name : str
            The name of the field for which the value is being validated.

        Raises
        ------
        ValueError
            If the value is not in the valid_list.
        """
        if value not in valid_list:
            msg = f"Invalid {name} value: {value}"
            raise ValueError(msg)

    def create(self, case_data: CaseDataType) -> str | tuple[dict | list | str, int]:
        """
        Create a new case using provided data.

        Parameters
        ----------
        case_data : CaseDataType
            Data for the new case.

        Returns
        -------
        str | tuple[dict, int]
            A success or error message, or a tuple containing the response and status code.

        Raises
        ------
        ValueError
            If input data validation fails
        """
        try:
            self._validate_inputs(case_data)

            data = {
                "title": case_data.title,
                "description": case_data.description,
                "severity": case_data.severity,
                "startDate": case_data.startDate,
                "endDate": case_data.endDate,
                "tags": case_data.tags,
                "flag": case_data.flag,
                "tlp": case_data.tlp,
                "pap": case_data.pap,
                "status": case_data.status,
                "summary": case_data.summary,
                "assignee": case_data.owner,
                "customFields": case_data.customFields,
                "tasks": case_data.stats.get("tasks"),
                "sharingParameters": case_data.stats.get("sharingParameters"),
            }

            if self._check_case_exist(case_data.title):
                self.logmanager.log(
                    "warning",
                    "A case with the same title already exists",
                    category="case_creation",
                    task_state="failed",
                )
                return "A case with the same title already exists"
            else:
                # Valores "vazios" padrão do CaseDataType (startDate=0 -> 1970, assignee="")
                # não são enviados, para o TheHive aplicar os próprios defaults.
                if not data["startDate"]:
                    data["startDate"] = None
                if not data["assignee"]:
                    data["assignee"] = None
                data = {k: v for k, v in data.items() if v is not None}
                response, status_code_request = self.session.request(
                    "case", method="POST", json_data=data
                )
                if 200 <= status_code_request < 300:
                    self.logmanager.log(
                        "info",
                        f"Case created successfully: {case_data.title}",
                        category="case_creation",
                        task_state="success",
                    )
                else:
                    self.logmanager.log(
                        "warning",
                        f"Failed to create case {case_data.title}. "
                        f"Status code: {status_code_request}",
                        category="case_creation",
                        task_state="failed",
                    )

                return response, status_code_request
        except ValueError as e:
            self.logmanager.log(
                "error",
                f"Input validation error: {e}",
                category="case_creation",
                task_state="failed",
            )
            raise
