from sadif.frameworks_drivers.log_manager.sadif_log import LogManager
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.list_case import (
    ListCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (
    SessionThehive,
)


class CaseLister:
    """
    Use case that lists TheHive cases (all pages) and filters them by tag.

    Parameters
    ----------
    thehive_session : SessionThehive
        An authenticated session to TheHive's API.
    """

    def __init__(self, thehive_session: SessionThehive):
        self.thehive_session = thehive_session
        self.logmanager = LogManager()

    def list_cases(self):
        try:
            list_case = ListCase(self.thehive_session)
            # range=all: sem ele o TheHive devolve só os 10 primeiros casos
            response, status = list_case.list_cases(case_range="all")

            if status == 200 and isinstance(response, list):
                self.logmanager.log(
                    "info", "Cases listed successfully.", category="thehive_case_listing"
                )
                return response
            else:
                msg = f"Error while listing cases: Status {status}"
                self.logmanager.log("error", msg, category="thehive_case_listing")
                raise Exception(msg)
        except Exception as e:
            self.logmanager.capture_exception(e, "Exception occurred in list_cases")
            raise

    def list_cases_by_tag(self, tag: str):
        try:
            all_cases = self.list_cases()
            cases_with_tag = [case for case in all_cases if tag in (case.get("tags") or [])]
            self.logmanager.log(
                "info", f"Cases filtered by tag: {tag}", category="thehive_case_filtering"
            )
            return cases_with_tag
        except Exception as e:
            self.logmanager.capture_exception(
                e, f"Exception occurred in list_cases_by_tag with tag: {tag}"
            )
            raise
