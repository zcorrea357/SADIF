from sadif.frameworks_drivers.log_manager.sadif_log import LogManager

log_manager = LogManager()

ALLOWED_CATEGORIES = {"crawler", "database", "network", "security", "yara", "cliente"}
if __name__ == "__main__":
    for i in range(10):
        log_manager.log(
            message="Division by zero error occurred.", level="debug", category="cliente"
        )
