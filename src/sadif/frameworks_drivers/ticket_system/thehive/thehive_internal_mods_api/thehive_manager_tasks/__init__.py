from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)


class Task:
    """
    Represents a task in TheHive.

    Attributes
    ----------
    session : SessionThehive
        A session instance used to communicate with TheHive.
    """

    def __init__(self, session: SessionThehive):
        """
        Initialize a Task instance.

        Parameters
        ----------
        session : SessionThehive
            An instance of the SessionThehive class.
        """
        self.session = session

    def create_task_in_case(
        self,
        caseId,
        title,
        group=None,
        description=None,
        status=None,
        flag=None,
        startDate=None,
        endDate=None,
        order=None,
        dueDate=None,
        assignee=None,
        mandatory=None,
    ):
        """
        Create a task within a specific case in TheHive.

        Parameters
        ----------
        caseId : str
            The ID of the case in which the task will be created.
        title : str
            The title of the task.
        group : str, optional
            The group of the task.
        description : str, optional
            A description of the task.
        status : str, optional
            The status of the task.
        flag : bool, optional
            A flag for the task.
        startDate : str, optional
            The start date of the task.
        endDate : str, optional
            The end date of the task.
        order : int, optional
            The order of the task.
        dueDate : str, optional
            The due date of the task.
        assignee : str, optional
            The assignee for the task.
        mandatory : bool, optional
            Whether the task is mandatory.

        Returns
        -------
        Response
            The response from the POST request.
        """

        # API v1: a v0 ("case/{id}/task") ignora mandatory e assignee. (O TheHive 5 ignora
        # "order" na criação nas duas APIs; use update_task para definir a posição.)
        endpoint = f"v1/case/{caseId}/task"

        # Building the request body
        data = {"title": title}

        if group:
            data["group"] = group
        if description:
            data["description"] = description
        if status:
            data["status"] = status
        if flag is not None:  # Checking for boolean values
            data["flag"] = flag
        if startDate:
            data["startDate"] = startDate
        if endDate:
            data["endDate"] = endDate
        if order is not None:  # order=0 is a valid position
            data["order"] = order
        if dueDate:
            data["dueDate"] = dueDate
        if assignee:
            data["assignee"] = assignee
        if mandatory is not None:  # Checking for boolean values
            data["mandatory"] = mandatory

        # Using the session to make the POST request
        return self.session.request(endpoint, method="POST", json_data=data)

    def get_task(self, taskId):
        """
        Retrieve a task by its ID from TheHive.

        Parameters
        ----------
        taskId : str
            The ID of the task.

        Returns
        -------
        Response
            The response from the GET request.
        """
        endpoint = f"v1/task/{taskId}"
        return self.session.request(endpoint, method="GET")

    def delete_task(self, taskId):
        """
        Delete a task by its ID in TheHive.

        Parameters
        ----------
        taskId : str
            The ID of the task to be deleted.

        Returns
        -------
        Response
            The response from the DELETE request.
        """
        endpoint = f"v1/task/{taskId}"
        return self.session.request(endpoint, method="DELETE")

    def update_task(
        self,
        taskId,
        title=None,
        group=None,
        description=None,
        status=None,
        flag=None,
        startDate=None,
        endDate=None,
        order=None,
        dueDate=None,
        assignee=None,
        mandatory=None,
    ):
        """
        Update a task by its ID in TheHive.

        Parameters
        ----------
        taskId : str
            The ID of the task to be updated.
        title : str, optional
            The new title for the task.
        group : str, optional
            The group for the task.
        description : str, optional
            The description for the task.
        status : str, optional
            The status for the task.
        flag : bool, optional
            The flag for the task.
        startDate : str, optional
            The start date for the task.
        endDate : str, optional
            The end date for the task.
        order : int, optional
            The order for the task.
        dueDate : str, optional
            The due date for the task.
        assignee : str, optional
            The assignee for the task.
        mandatory : bool, optional
            Whether the task is mandatory.

        Returns
        -------
        Response
            The response from the PATCH request.
        """

        endpoint = f"v1/task/{taskId}"

        data = {}
        if title:
            data["title"] = title
        if group:
            data["group"] = group
        if description is not None:  # Checking for nullable values
            data["description"] = description
        if status:
            data["status"] = status
        if flag is not None:
            data["flag"] = flag
        if startDate:
            data["startDate"] = startDate
        if endDate:
            data["endDate"] = endDate
        if order is not None:  # order=0 is a valid position
            data["order"] = order
        if dueDate:
            data["dueDate"] = dueDate
        if assignee is not None:  # Checking for nullable values
            data["assignee"] = assignee
        if mandatory is not None:
            data["mandatory"] = mandatory

        return self.session.request(endpoint, method="PATCH", json_data=data)

    def get_task_actions_required(self, taskId):
        """
        Retrieve actions required for a task by its ID from TheHive.

        Parameters
        ----------
        taskId : str
            The ID of the task.

        Returns
        -------
        Response
            The response from the GET request.
        """
        endpoint = f"v1/task/{taskId}/actionRequired"
        return self.session.request(endpoint, method="GET")
