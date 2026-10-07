import logging
from typing import Any, ClassVar

import sentry_sdk

from sadif.config.sadif_config import SadifConfiguration


class LogManager:
    """
    LogManager handles logging across the application, integrating with both the standard
    logging library and Sentry for error tracking.

    Attributes
    ----------
    ALLOWED_CATEGORIES : ClassVar[list[str]]
        A list of categories allowed for logging, to ensure logs are categorized correctly.
    TASK_STATES : ClassVar[list[str]]
        A list of task states to describe the status of tasks being logged.
    ALLOWED_CATEGORIES_BRANDING : ClassVar[list[str]]
        A list of categories specifically allowed for branding-related logs.

    Methods
    -------
    __init__(sentry_dsn: str = None, log_level: int = logging.DEBUG)
        Initializes the LogManager, setting up Sentry and the logging format.
    _validate_category(category: str)
        Validates the logging category against the allowed list.
    _validate_task_state(state: str)
        Validates the task state against the allowed list.
    log(level: str, message: str, category: str = "general", task_state: str = "none", exc_info: Optional[Any] = None)
        Logs a message with the specified level, category, and task state. Error logs are also sent to Sentry.
    add_breadcrumb(category: str, message: str, level: str = "info")
        Adds a breadcrumb to Sentry for context in error tracking.
    capture_exception(exception: Exception, message: str = "Exception captured", category: str = "general")
        Captures an exception with Sentry, tagging it with the specified category, and logs the associated message.
    """

    ALLOWED_CATEGORIES: ClassVar = [
        "crawler",
        "case_response_error",
        "webhook_notifications",
        "Database",
        "network",
        "security",
        "yara",
        "cliente",
        "observable_add_exception",
        "observable_add",
        "processing_error",
        "error_ticket_creation",
        "ticket_creation",
        "data_processing",
        "thehive_ticket",
        "thehive_case_listing",
        "thehive_case_filtering",
        "thehive_alert_creation",
        "thehive_alert_validation",
        "case_deletion",
        "case_creation",
        "case_update",
        "case_update_exception",
        "case_list",
        "case_list_exception",
        "case_response",
        "case_fetch",
        "case_fetch_exception",
        "Modules",
        "general",
        "yara",
        "file",
        "git",
        "export_manager",
        "import_manager",
        "crawler_manager",
        "module_manager",
        f"module_{SadifConfiguration().get_configuration('MONGODB_DATABASE_MODULES_MANAGER_RANSOMWHAT_NAME')}",
    ]
    TASK_STATES: ClassVar = [
        "none",
        "scheduled",
        "queued",
        "success",
        "running",
        "restarting",
        "failed",
        "skipped",
        "upstream_failed",
        "up_for_retry",
        "up_for_reschedule",
        "deferred",
        "removed",
    ]
    LOG_LEVELS: ClassVar = ["debug", "info", "warning", "error", "critical"]
    _sentry_dsn: ClassVar[Any] = None
    _sentry_initialized: ClassVar[bool] = False
    ALLOWED_CATEGORIES_BRANDING: ClassVar = [
        "Name",
        "Country",
        "Google_Play_ID",
        "Language",
        "Legal_Entity",
        "Logo",
        "Tax_ID",
        "Web_Domain",
        "case_response_error",
    ]

    def __init__(self, log_level: int = logging.DEBUG):
        """
        Initializes the LogManager, setting up Sentry for error tracking and configuring
        the standard logging format.

        Parameters
        ----------
        log_level : int
            The minimum log level for messages to handle, defaults to logging.DEBUG.
        """
        self.sadif_config = SadifConfiguration()

        sentry_dsn = self.sadif_config.get_configuration("SENTRYDSN")
        # Reinicializar o Sentry a cada instância descartaria o cliente anterior sem
        # fechá-lo; só reinicializa quando o DSN configurado muda.
        if not LogManager._sentry_initialized or LogManager._sentry_dsn != sentry_dsn:
            sentry_sdk.init(dsn=sentry_dsn)
            LogManager._sentry_dsn = sentry_dsn
            LogManager._sentry_initialized = True
        log_format = "%(asctime)s - [%(levelname)s] - [%(name)s] - %(message)s - Source: %(filename)s:%(lineno)d"
        logging.basicConfig(level=log_level, format=log_format, datefmt="%Y-%m-%d %H:%M:%S")

    def _validate_category(self, category: str):
        """
        Validates the logging category against the allowed list. Raises a ValueError if the category is not allowed.

        Parameters
        ----------
        category : str
            The category to validate.
        """
        if category not in self.ALLOWED_CATEGORIES + self.ALLOWED_CATEGORIES_BRANDING:
            msg = f"Invalid category: {category}. Allowed categories are: {self.ALLOWED_CATEGORIES}"
            raise ValueError(msg)

    def _validate_task_state(self, state: str):
        """
        Validates the task state against the allowed list. Raises a ValueError if the state is not allowed.

        Parameters
        ----------
        state : str
            The task state to validate.
        """
        if state not in self.TASK_STATES:
            msg = f"Invalid task state: {state}. Allowed states are: {self.TASK_STATES}"
            raise ValueError(msg)

    def _validate_level(self, level: str) -> str:
        """
        Validates the log level against LOG_LEVELS (case-insensitive) and returns it in lowercase.
        Raises a ValueError if the level is not allowed.
        """
        normalized = level.lower() if isinstance(level, str) else level
        if normalized not in self.LOG_LEVELS:
            msg = f"Invalid log level: {level}. Allowed levels are: {self.LOG_LEVELS}"
            raise ValueError(msg)
        return normalized

    def log(
        self,
        level: str,
        message: str,
        category: str = "general",
        task_state: str = "none",
        exc_info: Any | None = None,
    ):
        """
        Logs a message with the specified level, category, and task state. Error logs are also sent to Sentry.

        Parameters
        ----------
        level : str
            The severity level of the log ('debug', 'info', 'warning', 'error', 'critical').
        message : str
            The log message.
        category : str
            The category of the log, defaults to 'general'.
        task_state : str
            The state of the task being logged, defaults to 'none'.
        exc_info : Optional[Any]
            Additional exception information for error logs, defaults to None.
        """
        level = self._validate_level(level)
        self._validate_category(category)
        self._validate_task_state(task_state)

        formatted_message = f"[{task_state.upper()}] - {message}"
        logger = logging.getLogger(category)

        if level == "error" and exc_info:
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("category", category)
                logger.error(formatted_message, exc_info=exc_info)
                sentry_sdk.capture_exception(exc_info)
        else:
            getattr(logger, level)(formatted_message, exc_info=exc_info)

    def add_breadcrumb(self, category: str, message: str, level: str = "info"):
        """
        Adds a breadcrumb to Sentry for context in error tracking.

        Parameters
        ----------
        category : str
            The category of the breadcrumb.
        message : str
            The message for the breadcrumb.
        level : str
            The severity level of the breadcrumb ('debug', 'info', 'warning', 'error', 'critical').
        """
        if level not in [*self.LOG_LEVELS, "fatal"]:
            msg = f"Invalid breadcrumb level: {level}. Allowed levels are: {[*self.LOG_LEVELS, 'fatal']}"
            raise ValueError(msg)
        self._validate_category(category)
        sentry_sdk.add_breadcrumb(category=category, message=message, level=level)

    def capture_exception(
        self, exception: Exception, message: str = "Exception captured", category: str = "general"
    ):
        """
        Captures an exception with Sentry, tagging it with the specified category, and logs the associated message.

        Parameters
        ----------
        exception : Exception
            The exception to capture.
        message : str
            The message to log along with the exception capture.
        category : str
            The category for the log and Sentry tag, defaults to 'general'.
        """
        self._validate_category(category)
        # log() registra a mensagem e envia a exceção ao Sentry com a tag da categoria
        self.log("error", message, exc_info=exception, category=category)
