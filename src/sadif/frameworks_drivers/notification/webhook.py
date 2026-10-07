import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import requests
from requests.exceptions import InvalidURL, RequestException

from sadif.frameworks_drivers.log_manager.sadif_log import LogManager


class WebhookSender:
    """
    A utility class for sending data to a specified webhook URL. It supports retrying
    on failure, specifying proxies, and invoking callback functions on success or failure.

    Attributes
    ----------
    url : str
        The webhook URL to send data to.
    timeout : int
        The timeout for the webhook request in seconds.
    max_retries : int
        The maximum number of retry attempts for sending the webhook.
    proxies : Optional[Dict[str, str]]
        A dictionary of proxies to use for the request.
    success_callback : Optional[Callable]
        A callback function to be called on successful request completion.
    failure_callback : Optional[Callable]
        A callback function to be called on request failure.

    Methods
    -------
    __init__(self, url, timeout=10, max_retries=3, proxies=None, success_callback=None, failure_callback=None)
        Initializes the WebhookSender with the specified configuration.
    validate_url(self)
        Validates the webhook URL.
    send(self, data, headers=None, method="POST")
        Sends the specified data to the webhook URL using the HTTP method provided.
    """

    def __init__(
        self,
        url: str,
        timeout: float = 10,
        max_retries: int = 3,
        proxies: dict[str, str] | None = None,
        success_callback: Callable | None = None,
        failure_callback: Callable | None = None,
    ):
        """
        Initializes the WebhookSender with the specified parameters.

        Parameters
        ----------
        url : str
            The URL of the webhook to send data to.
        timeout : int
            The timeout in seconds for the requests.
        max_retries : int
            The maximum number of retries for the request in case of failure.
        proxies : Optional[Dict[str, str]]
            A dictionary specifying the HTTP and/or HTTPS proxies to use for the requests.
        success_callback : Optional[Callable]
            A callback function that gets called if the request is successful.
        failure_callback : Optional[Callable]
            A callback function that gets called if the request fails.
        """
        self.url = url
        self.timeout = timeout
        self.max_retries = max_retries
        self.proxies = proxies
        self.success_callback = success_callback
        self.failure_callback = failure_callback
        self.logmanager = LogManager()
        self.validate_url()

    def validate_url(self) -> bool:
        """
        Validates the webhook URL to ensure it is well-formed.

        Returns
        -------
        bool
            True if the URL is valid, False otherwise.
        """
        parsed_url = urlparse(self.url)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            self.logmanager.log(
                "error",
                "Invalid URL provided to WebhookSender",
                category="webhook_notifications",
                task_state="failed",
            )
            return False  # Or raise ValueError("Invalid URL provided to WebhookSender.")
        return True

    def send(
        self, data: Any, headers: dict[str, str] | None = None, method: str = "POST"
    ) -> requests.Response | None:
        """
        Sends data to the configured webhook URL.

        Parameters
        ----------
        data : Any
            The data to send to the webhook. Dicts and lists are JSON-encoded; strings and
            bytes are sent as-is.
        headers : Optional[Dict[str, str]]
            Additional headers to include in the request. They are merged over the default
            JSON Content-Type (a custom Content-Type overrides it).
        method : str
            The HTTP method to use for the request. Defaults to "POST".

        Returns
        -------
        Optional[requests.Response]
            The response from the webhook server if successful, None otherwise.

        Raises
        ------
        RequestException
            If all attempts to send the request fail.
        InvalidURL
            If the configured URL is not well-formed (no request is attempted).
        """
        if not self.validate_url():
            message = f"Invalid URL provided to WebhookSender: {self.url!r}"
            raise InvalidURL(message)
        headers = {"Content-Type": "application/json", **(headers or {})}

        current_timeout = self.timeout
        attempts = max(1, self.max_retries)
        for attempt in range(attempts):
            try:
                response = requests.request(
                    method,
                    self.url,
                    data=json.dumps(data) if isinstance(data, dict | list) else data,
                    headers=headers,
                    timeout=current_timeout,
                    proxies=self.proxies,
                )
                response.raise_for_status()
                if self.success_callback:
                    self.success_callback(response)
                self.logmanager.log(
                    "info",
                    f"Webhook successfully sent to {self.url}",
                    category="webhook_notifications",
                    task_state="success",
                )
                return response
            except RequestException as e:
                self.logmanager.log(
                    "warning",
                    f"Attempt {attempt + 1} failed: {e}",
                    category="webhook_notifications",
                    task_state="up_for_retry",
                )
                if self.failure_callback:
                    self.failure_callback(e)
                current_timeout *= 2
                if attempt == attempts - 1:
                    self.logmanager.log(
                        "error",
                        "All attempts to send the webhook failed",
                        category="webhook_notifications",
                        task_state="failed",
                    )
                    raise
        return None


# Example usage
if __name__ == "__main__":

    def on_success(response):
        print(f"Success: {response.request.url}")

    def on_failure(exception):
        print(f"Failure: {exception}")

    webhook_url = "https://dsa.requestcatcher.com/"
    webhook_sender = WebhookSender(
        webhook_url, max_retries=5, success_callback=on_success, failure_callback=on_failure
    )
    data = {"message": "Hello, world!"}
    try:
        response = webhook_sender.send(data, method="POST")
    except RequestException:
        print("All attempts to send the webhook failed.")
