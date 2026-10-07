# Example usage
from requests import RequestException

from sadif.frameworks_drivers.notification.webhook import WebhookSender

if __name__ == "__main__":

    def on_success(response):
        print(f"Success: {response.request.url}")

    def on_failure(exception):
        print(f"Failure: {exception}")

    webhook_url = "https://httpbin.org/post"
    webhook_sender = WebhookSender(
        webhook_url, max_retries=5, success_callback=on_success, failure_callback=on_failure
    )
    data = {"message": "Hello, world!"}
    try:
        response = webhook_sender.send(data, method="POST")
    except RequestException:
        print("All attempts to send the webhook failed.")
