from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class CaseResponse:
    """
    Represents the response from a case API.

    Attributes:
        status_code (int): The HTTP status code of the response.
        _id (str): The unique ID of the case.
        ... [other attributes] ...
        error_type (str): Type of error (if any).
        error_message (str): Detailed error message (if any).

    Note:
        The attributes starting with an underscore (`_`) such as `_id` and `_type`
        are usually considered private by convention in Python, even though
        they are not strictly private.
    """

    def __init__(self, status_code, response_data):
        self.logmanager = LogManager()
        """
        Initializes a CaseResponse object.

        Args:
            status_code (int): The HTTP status code of the response.
            response_data (dict): The response data from the API.
        """
        self.status_code = status_code
        # If it's a successful response
        if self.is_success():
            self._id = response_data.get("_id")
            self._type = response_data.get("_type")
            self._createdBy = response_data.get("_createdBy")
            self._updatedBy = response_data.get("_updatedBy")
            self._createdAt = response_data.get("_createdAt")
            self._updatedAt = response_data.get("_updatedAt")
            self.number = response_data.get("number")
            self.title = response_data.get("title")
            self.description = response_data.get("description")
            self.severity = response_data.get("severity")
            self.severityLabel = response_data.get("severityLabel")
            self.startDate = response_data.get("startDate")
            self.endDate = response_data.get("endDate")
            self.tags = response_data.get("tags", [])
            self.flag = response_data.get("flag")
            self.tlp = response_data.get("tlp")
            self.tlpLabel = response_data.get("tlpLabel")
            self.pap = response_data.get("pap")
            self.papLabel = response_data.get("papLabel")
            self.status = response_data.get("status")
            self.stage = response_data.get("stage")
            self.summary = response_data.get("summary")
            self.impactStatus = response_data.get("impactStatus")
            self.assignee = response_data.get("assignee")
            self.customFields = response_data.get("customFields", [])
            self.userPermissions = response_data.get("userPermissions", [])
            self.extraData = response_data.get("extraData")
            self.newDate = response_data.get("newDate")
            self.inProgressDate = response_data.get("inProgressDate")
            self.closedDate = response_data.get("closedDate")
            self.alertDate = response_data.get("alertDate")
            self.alertNewDate = response_data.get("alertNewDate")
            self.alertInProgressDate = response_data.get("alertInProgressDate")
            self.alertImportedDate = response_data.get("alertImportedDate")
            self.timeToDetect = response_data.get("timeToDetect")
            self.timeToTriage = response_data.get("timeToTriage")
            self.timeToQualify = response_data.get("timeToQualify")
            self.timeToAcknowledge = response_data.get("timeToAcknowledge")
            self.timeToResolve = response_data.get("timeToResolve")
            self.handlingDuration = response_data.get("handlingDuration")
            self.logmanager.log(
                "info",
                f"Successfully processed case response: {self.title}",
                category="case_response",
                task_state="success",
            )

        else:
            self.error_type = response_data.get("type")
            self.error_message = response_data.get("message")
            self.logmanager.log(
                "error",
                f"Error processing case response: {self.error_message}",
                category="case_response_error",
                task_state="failed",
            )

    def is_success(self):
        """
        Determines if the response was successful.

        Returns:
            bool: True if the status code is 200, otherwise False.
        """
        return self.status_code == 200

    def __str__(self):
        """
        Returns a string representation of the CaseResponse object.

        Returns:
            str: A string representation of the CaseResponse
        """
        if self.is_success():
            return f"Case: {self.title} - {self.description}"
        else:
            return f"Error ({self.status_code}): {self.error_type} - {self.error_message}"


# documente a class numpy, com suporte a notes para a ferramenta pdoc
