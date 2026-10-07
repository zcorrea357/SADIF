from sadif.frameworks_drivers.log_manager.sadif_log import LogManager
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)

# Tipos de observable cujo conteúdo é um arquivo: o TheHive exige upload multipart, que a
# SessionThehive (só JSON) não faz. Enviados como JSON, o TheHive responde 201 com uma
# lista vazia sem criar nada, então são recusados explicitamente.
ATTACHMENT_DATA_TYPES = frozenset({"file"})


def _reject_attachment_type(data_type) -> None:
    if data_type in ATTACHMENT_DATA_TYPES:
        msg = (
            f"Observable dataType {data_type!r} requires a multipart file upload, "
            "which is not supported; use a non-attachment dataType (e.g. 'filename' or 'hash')"
        )
        raise ValueError(msg)


class Observable:
    """
    A utility class to manage observables related to cases and alerts in TheHive.

    Attributes
    ----------
    session : SessionThehive
        An active session to interact with TheHive's API.

    Methods
    -------
    add_to_case(case_id, data_type, ...):
        Add an observable to a specific case.

    add_to_alert(alert_id, data_type, ...):
        Add an observable to a specific alert.

    get_observable(observable_id):
        Fetch the details of a specific observable.

    delete_observable(observable_id):
        Delete a specific observable.

    update_observable(observable_id, data_type, ...):
        Update the details of a specific observable.

    """

    def __init__(self, session: SessionThehive):
        """
        Initialize the Observable object.

        Parameters
        ----------
        session : SessionThehive
            An active session to interact with TheHive's API.
        """
        self.session = session
        self.logmanager = LogManager()

    def add_to_case(
        self,
        case_id,
        data_type,
        data=None,
        message=None,
        start_date=None,
        attachment=None,
        tlp=2,
        pap=2,
        tags=None,
        ioc=False,
        sighted=False,
        sighted_at=None,
        ignore_similarity=False,
        is_zip=False,
        zip_password=None,
    ):
        """
        Add an observable to a specific case in TheHive.

        Parameters
        ----------
        case_id : str
            The unique identifier of the case to which the observable should be added.
        data_type : str
            The type of data the observable represents (e.g., 'ip', 'hash', 'domain').
        data : str, optional
            The actual data for the observable (e.g., an IP address, file hash, etc.).
        message : str, optional
            An optional message or description about the observable.
        start_date : str, optional
            The date when the observable was first seen.
        attachment : str, optional
            If the observable has an associated attachment, its name goes here.
        tlp : int, optional (default=2)
            Traffic Light Protocol level, it defines data sharing restrictions.
        pap : int, optional (default=2)
            Permissible Actions Protocol level.
        tags : list of str, optional
            List of tags associated with the observable.
        ioc : bool, optional (default=False)
            Indicates if the observable is an Indicator of Compromise.
        sighted : bool, optional (default=False)
            Indicates if the observable was sighted in your environment.
        sighted_at : str, optional
            The date when the observable was sighted.
        ignore_similarity : bool, optional (default=False)
            Whether or not to ignore similarities with other observables.
        is_zip : bool, optional (default=False)
            Indicates if the observable is in a ZIP archive.
        zip_password : str, optional
            If the observable is in a ZIP, its password can be specified here.

        Returns
        -------
        tuple
            The response and status code from the API request to add the observable to the case.

        Raises
        ------
        ValueError
            If data_type is an attachment type (e.g. 'file'), which needs a multipart upload.
        """
        _reject_attachment_type(data_type)

        # Construct the URL
        endpoint = f"v1/case/{case_id}/observable"

        # Construct the request payload
        payload = {
            "dataType": data_type,
            "data": data,
            "message": message,
            "startDate": start_date,
            "attachment": attachment,
            "tlp": tlp,
            "pap": pap,
            "tags": tags,
            "ioc": ioc,
            "sighted": sighted,
            "sightedAt": sighted_at,
            "ignoreSimilarity": ignore_similarity,
            "isZip": is_zip,
            "zipPassword": zip_password,
        }

        # Filter out None values
        payload = {k: v for k, v in payload.items() if v is not None}

        # Send the request using the session
        return self.session.request(endpoint, method="POST", json_data=payload)

    def add_to_alert(
        self,
        alert_id,
        data_type,
        data=None,
        message=None,
        start_date=None,
        attachment=None,
        tlp=2,
        pap=2,
        tags=None,
        ioc=False,
        sighted=False,
        sighted_at=None,
        ignore_similarity=False,
        is_zip=False,
        zip_password=None,
    ):
        """
        Add an observable to a specific alert in TheHive.

        Parameters
        ----------
        alert_id : str
            The unique identifier of the alert to which the observable should be added.
        data_type : str
            The type of data the observable represents (e.g., 'ip', 'hash', 'domain').
        data : str, optional
            The actual data for the observable (e.g., an IP address, file hash, etc.).
        message : str, optional
            An optional message or description about the observable.
        start_date : str, optional
            The date when the observable was first seen.
        attachment : str, optional
            If the observable has an associated attachment, its name goes here.
        tlp : int, optional (default=2)
            Traffic Light Protocol level, it defines data sharing restrictions.
        pap : int, optional (default=2)
            Permissible Actions Protocol level.
        tags : list of str, optional
            List of tags associated with the observable.
        ioc : bool, optional (default=False)
            Indicates if the observable is an Indicator of Compromise.
        sighted : bool, optional (default=False)
            Indicates if the observable was sighted in your environment.
        sighted_at : str, optional
            The date when the observable was sighted.
        ignore_similarity : bool, optional (default=False)
            Whether or not to ignore similarities with other observables.
        is_zip : bool, optional (default=False)
            Indicates if the observable is in a ZIP archive.
        zip_password : str, optional
            If the observable is in a ZIP, its password can be specified here.

        Returns
        -------
        tuple
            The response and status code from the API request to add the observable to the alert.

        Raises
        ------
        ValueError
            If data_type is an attachment type (e.g. 'file'), which needs a multipart upload.
        """
        _reject_attachment_type(data_type)
        try:
            # Construct the URL
            endpoint = f"v1/alert/{alert_id}/observable"

            # Construct the request payload
            payload = {
                "dataType": data_type,
                "data": data,
                "message": message,
                "startDate": start_date,
                "attachment": attachment,
                "tlp": tlp,
                "pap": pap,
                "tags": tags,
                "ioc": ioc,
                "sighted": sighted,
                "sightedAt": sighted_at,
                "ignoreSimilarity": ignore_similarity,
                "isZip": is_zip,
                "zipPassword": zip_password,
            }
            payload = {k: v for k, v in payload.items() if v is not None}

            response, status = self.session.request(endpoint, method="POST", json_data=payload)

            # 201 = criado; 207 (multi-status) = o TheHive recusou o observable (ex.: duplicado).
            if status in (200, 201):
                self.logmanager.log(
                    "info",
                    f"Observable added to alert {alert_id} successfully.",
                    category="observable_add",
                    task_state="success",
                )
            else:
                self.logmanager.log(
                    "warning",
                    f"Failed to add observable to alert {alert_id}. Status code: {status} ({response})",
                    category="observable_add",
                    task_state="failed",
                )

            return response, status
        except Exception as e:
            self.logmanager.log(
                "error",
                f"Exception occurred while adding observable to alert {alert_id}: {e}",
                category="observable_add_exception",
                task_state="failed",
            )
            self.logmanager.capture_exception(e)
            raise

    def get_observable(self, observable_id):
        """
        Fetch the details of a specific observable.

        Parameters
        ----------
        observable_id : str
            The ID of the observable to be fetched.

        Returns
        -------
        tuple
            The response and status code of the request.
        """
        endpoint = f"v1/observable/{observable_id}"
        # Fetch the observable details using the session
        return self.session.request(endpoint, method="GET")

    def delete_observable(self, observable_id):
        """
        Delete a specific observable.

        Parameters
        ----------
        observable_id : str
            The ID of the observable to be deleted.

        Returns
        -------
        tuple
            The response and status code of the delete request
        """  # Construct the URL
        endpoint = f"v1/observable/{observable_id}"

        # Delete the observable using the session
        return self.session.request(endpoint, method="DELETE")

    def update_observable(
        self,
        observable_id,
        data_type,
        message=None,
        tlp=None,
        pap=None,
        tags=None,
        ioc=None,
        sighted=None,
        sighted_at=None,
        ignore_similarity=None,
        add_tags=None,
        remove_tags=None,
    ):
        """
        Update the details of a specific observable in TheHive.

        Parameters
        ----------
        observable_id : str
            The unique identifier of the observable to be updated.
        data_type : str
            The type of data the observable represents (e.g., 'ip', 'hash', 'domain').
        message : str, optional
            An updated message or description about the observable.
        tlp : int, optional
            Updated Traffic Light Protocol level, it defines data sharing restrictions.
        pap : int, optional
            Updated Permissible Actions Protocol level.
        tags : list of str, optional
            Updated list of tags associated with the observable.
        ioc : bool, optional
            Indicates if the updated observable is an Indicator of Compromise.
        sighted : bool, optional
            Indicates if the updated observable was sighted in your environment.
        sighted_at : str, optional
            The updated date when the observable was sighted.
        ignore_similarity : bool, optional
            Whether or not to ignore similarities with other observables in the updated observable.
        add_tags : list of str, optional
            List of tags to add to the observable.
        remove_tags : list of str, optional
            List of tags to remove from the observable.

        Returns
        -------
        tuple
            The response and status code from the API request to update the observable.

        """
        # Construct the URL
        endpoint = f"v1/observable/{observable_id}"

        # Construct the request payload
        payload = {
            "dataType": data_type,
            "message": message,
            "tlp": tlp,
            "pap": pap,
            "tags": tags,
            "ioc": ioc,
            "sighted": sighted,
            "sightedAt": sighted_at,
            "ignoreSimilarity": ignore_similarity,
            "addTags": add_tags,
            "removeTags": remove_tags,
        }

        # Filter out None values
        payload = {k: v for k, v in payload.items() if v is not None}

        # Send the request using the session
        return self.session.request(endpoint, method="PATCH", json_data=payload)
