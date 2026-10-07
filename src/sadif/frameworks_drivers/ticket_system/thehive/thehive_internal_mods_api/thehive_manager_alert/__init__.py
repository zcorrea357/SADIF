from sadif.frameworks_drivers.log_manager.sadif_log import LogManager
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)


class Alert:
    """
    Classe para representar um alerta no TheHive.

    Args:
        session (SessionThehive): Uma instância de SessionThehive para comunicação com o TheHive.

    Attributes:
        session (SessionThehive): A sessão para comunicação com o TheHive.
    """

    def __init__(self, session: SessionThehive):
        self.session = session
        self.logmanager = LogManager()

    def create(
        self,
        alert_type: str,
        source: str,
        sourceRef: str,
        title: str,
        description: str,
        externalLink=None,
        severity=None,
        date=None,
        tags=None,
        flag=None,
        tlp=None,
        pap=None,
        customFields=None,
        summary=None,
        status=None,
        assignee=None,
        caseTemplate=None,
        observables=None,
        procedures=None,
    ):
        """
        Cria um alerta no TheHive.

        Args:
            alert_type (str): O tipo do alerta.
            source (str): A fonte do alerta.
            sourceRef (str): A referência da fonte do alerta.
            title (str): O título do alerta.
            description (str): A descrição do alerta.
            externalLink (str, optional): O link externo associado ao alerta.
            severity (str, optional): A gravidade do alerta.
            date (str, optional): A data do alerta.
            tags (list, optional): Uma lista de tags associadas ao alerta.
            flag (str, optional): A bandeira associada ao alerta.
            tlp (int, optional): O TLP (Traffic Light Protocol) associado ao alerta.
            pap (int, optional): O PAP (Permisssions and Administration Protocol) associado ao alerta.
            customFields (dict, optional): Campos personalizados associados ao alerta.
            summary (str, optional): O resumo do alerta.
            status (str, optional): O status do alerta.
            assignee (str, optional): O destinatário do alerta.
            caseTemplate (str, optional): O modelo de caso associado ao alerta.
            observables (list, optional): Uma lista de observáveis associados ao alerta.
            procedures (list, optional): Uma lista de procedimentos associados ao alerta.

        Returns:
            dict: Os dados do alerta criado no TheHive

        Raises:
            AssertionError: Se os campos obrigatórios não forem strings dentro dos limites de tamanho
                especificados, ou se severity (1-4), tlp (0-4) ou pap (0-3) forem inválidos.
        """
        try:
            # Checando o tamanho dos campos obrigatórios. Usa raise explícito (e não assert)
            # para a validação não sumir com "python -O" e ser registrada no log abaixo.
            self._check_length(alert_type, 1, 32, "alert_type")
            self._check_length(source, 1, 32, "source")
            self._check_length(sourceRef, 1, 128, "sourceRef")
            self._check_length(title, 1, 512, "title")
            self._check_length(description, 0, 1048576, "description")
            self._check_choice(severity, (1, 2, 3, 4), "severity")
            self._check_choice(tlp, (0, 1, 2, 3, 4), "tlp")
            self._check_choice(pap, (0, 1, 2, 3), "pap")

            # Formando o payload
            data = {
                "type": alert_type,
                "source": source,
                "sourceRef": sourceRef,
                "title": title,
                "description": description,
            }
            optional_fields = {
                "externalLink": externalLink,
                "severity": severity,
                "date": date,
                "tags": tags,
                "flag": flag,
                "tlp": tlp,
                "pap": pap,
                "customFields": customFields,
                "summary": summary,
                "status": status,
                "assignee": assignee,
                "caseTemplate": caseTemplate,
                "observables": observables,
                "procedures": procedures,
            }
            # "is not None" (e não truthiness): tlp=0 (TLP:CLEAR), pap=0 e flag=False são válidos.
            # Listas/dicionários vazios continuam omitidos.
            for key, value in optional_fields.items():
                if value is None or (isinstance(value, list | dict | str) and not value):
                    continue
                data[key] = value

            response = self.session.create_alert(data)

            status_code = response[1] if isinstance(response, tuple) and len(response) == 2 else 0
            if isinstance(status_code, int) and 200 <= status_code < 300:
                self.logmanager.log(
                    "info",
                    f"Alert created successfully in TheHive: {sourceRef}",
                    category="thehive_alert_creation",
                    task_state="success",
                )
            else:
                self.logmanager.log(
                    "warning",
                    f"TheHive did not create the alert {sourceRef}: {response}",
                    category="thehive_alert_creation",
                    task_state="failed",
                )
            return response

        except AssertionError as e:
            self.logmanager.log(
                "error",
                f"Input validation failed: {e}",
                category="thehive_alert_validation",
                task_state="failed",
            )
            raise

        except Exception as e:
            self.logmanager.capture_exception(e, "Exception occurred in Alert creation")
            raise

    @staticmethod
    def _check_length(value, min_len: int, max_len: int, name: str) -> None:
        if not isinstance(value, str) or not min_len <= len(value) <= max_len:
            length = len(value) if isinstance(value, str) else type(value).__name__
            msg = f"{name} must be a string with {min_len}..{max_len} characters, got {length}"
            raise AssertionError(msg)

    @staticmethod
    def _check_choice(value, choices: tuple, name: str) -> None:
        if value is not None and (isinstance(value, bool) or value not in choices):
            msg = f"Invalid {name} value: {value!r} (expected one of {choices})"
            raise AssertionError(msg)
