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
            AssertionError: Se os tamanhos dos campos obrigatórios não estiverem dentro dos limites especificados.
        """
        # Checando o tamanho dos campos obrigatórios
        assert 1 <= len(alert_type) <= 32
        assert 1 <= len(source) <= 32
        assert 1 <= len(sourceRef) <= 128
        assert 1 <= len(title) <= 512
        assert len(description) <= 1048576

        # Formando o payload
        data = {
            "type": alert_type,
            "source": source,
            "sourceRef": sourceRef,
            "title": title,
            "description": description,
        }
        try:
            if externalLink:
                data["externalLink"] = externalLink
            if severity:
                data["severity"] = severity
            if date:
                data["date"] = date
            if tags:
                data["tags"] = tags
            if flag:
                data["flag"] = flag
            if tlp:
                data["tlp"] = tlp
            if pap:
                data["pap"] = pap
            if customFields:
                data["customFields"] = customFields
            if summary:
                data["summary"] = summary
            if status:
                data["status"] = status
            if assignee:
                data["assignee"] = assignee
            if caseTemplate:
                data["caseTemplate"] = caseTemplate
            if observables:
                data["observables"] = observables
            if procedures:
                data["procedures"] = procedures

            response = self.session.create_alert(data)

            self.logmanager.log(
                "info",
                "Alert created successfully in TheHive",
                category="thehive_alert_creation",
                task_state="success",
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
