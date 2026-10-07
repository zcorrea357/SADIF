import sys

import typer

app = typer.Typer(help="SADIF command line interface.")

existing_usernames = ["rick", "morty"]


@app.command("create")
def create_user(username: str):
    """Create a user (prints a message if it already exists)."""
    if username in existing_usernames:
        print("The user already exists")
    else:
        existing_usernames.append(username)
        print(f"User created: {username}")


@app.command("notify")
def send_notification(username: str):
    """Send a notification to an existing user."""
    if username not in existing_usernames:
        print("User not found")
    else:
        print(f"Notification sent for user: {username}")


def main():
    try:
        while True:
            command = input("Enter command (create, notify, exit): ").strip()
            if command == "exit":
                print("Exiting...")
                break
            elif command == "create":  # noqa: RET508
                username = input("Enter username to create: ").strip()
                create_user(username)
            elif command == "notify":
                username = input("Enter username to notify: ").strip()
                send_notification(username)
            else:
                print("Invalid command")
    except EOFError:  # stdin fechado (ex.: pipe): encerra como "exit"
        print("Exiting...")


if __name__ == "__main__":
    # Com argumentos usa os subcomandos (python -m sadif.cli create rick); sem, o modo interativo.
    if len(sys.argv) > 1:
        app()
    else:
        main()
