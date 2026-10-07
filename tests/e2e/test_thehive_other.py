import pytest

pytestmark = pytest.mark.e2e

import string  # noqa: E402
import time  # noqa: E402

from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_alert import (  # noqa: E402
    Alert,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case_comment_template import (  # noqa: E402
    CaseCommentTemplate,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case_comment_template.template_render import (  # noqa: E402
    TemplateRenderer,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_comment import (  # noqa: E402
    CaseComment,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_markdown import (  # noqa: E402
    MarkdownConverter,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_observable import (  # noqa: E402
    Observable,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_tasks import (  # noqa: E402
    Task,
)

SERVICE_USER = "sadif@thehive.local"
MISSING_ID = "~999999999"

# Exemplo de valor para cada tipo de observable (não-anexo) padrão do TheHive 5.
OBSERVABLE_SAMPLES = {
    "autonomous-system": "AS{uid}",
    "domain": "{uid}.example.org",
    "filename": "{uid}.exe",
    "fqdn": "host.{uid}.example.org",
    "hash": "d41d8cd98f00b204e9800998{uid8}",
    "hostname": "host-{uid}",
    "ip": "10.{a}.{b}.{c}",
    "mail": "{uid}@example.org",
    "mail-subject": "Fatura {uid}",
    "other": "other-{uid}",
    "regexp": "^{uid}.*$",
    "registry": "HKLM\\Software\\{uid}",
    "uri_path": "/path/{uid}",
    "url": "http://127.0.0.1/{uid}",
    "user-agent": "Mozilla/5.0 ({uid})",
}


def sample_for(data_type: str, e2e_id: str) -> str:
    digits = int(e2e_id[3:], 16)
    return OBSERVABLE_SAMPLES[data_type].format(
        uid=e2e_id,
        uid8=e2e_id[-8:],
        a=digits % 250,
        b=(digits // 250) % 250,
        c=(digits // 62500) % 250,
    )


def query(session, *steps):
    body, status = session.request("v1/query", method="POST", json_data={"query": list(steps)})
    assert status == 200, body
    return body


def case_observables(session, case_id):
    return query(session, {"_name": "getCase", "idOrName": case_id}, {"_name": "observables"})


def alert_observables(session, alert_id):
    return query(session, {"_name": "getAlert", "idOrName": alert_id}, {"_name": "observables"})


def case_comments(session, case_id):
    return query(session, {"_name": "getCase", "idOrName": case_id}, {"_name": "comments"})


def alerts_by_source_ref(session, source_ref):
    return query(
        session,
        {"_name": "listAlert"},
        {"_name": "filter", "_eq": {"_field": "sourceRef", "_value": source_ref}},
    )


# ------------------------------------------------------------------------- fixtures


@pytest.fixture()
def case_factory(thehive_session, e2e_id):
    """Cria casos direto na API v1 e apaga todos ao final."""
    created = []

    def make(suffix="case"):
        body, status = thehive_session.request(
            "v1/case",
            method="POST",
            json_data={"title": f"{e2e_id} {suffix}", "description": "e2e", "tags": [e2e_id]},
        )
        assert status == 201, body
        created.append(body["_id"])
        return body

    yield make
    for case_id in created:
        thehive_session.request(f"v1/case/{case_id}", method="DELETE")


@pytest.fixture()
def case(case_factory):
    return case_factory()


@pytest.fixture()
def alert_cleanup(thehive_session):
    """Lista de ids de alertas a apagar ao final do teste."""
    ids = []
    yield ids
    for alert_id in ids:
        thehive_session.request(f"v1/alert/{alert_id}", method="DELETE")


@pytest.fixture()
def raw_alert(thehive_session, e2e_id, alert_cleanup):
    """Alerta criado direto na API v1 (independente da classe Alert)."""
    body, status = thehive_session.request(
        "v1/alert",
        method="POST",
        json_data={
            "type": "e2e",
            "source": "sadif-e2e",
            "sourceRef": f"raw-{e2e_id}",
            "title": f"{e2e_id} raw alert",
            "description": "e2e",
        },
    )
    assert status == 201, body
    alert_cleanup.append(body["_id"])
    return body


@pytest.fixture()
def case_template(thehive_session, e2e_id):
    name = f"tpl-{e2e_id}"
    body, status = thehive_session.request(
        "v1/caseTemplate", method="POST", json_data={"name": name, "description": "e2e"}
    )
    assert status == 201, body
    yield name
    thehive_session.request(f"v1/caseTemplate/{body['_id']}", method="DELETE")


# ---------------------------------------------------------------------------- Alert


def test_alert_create_minimal(thehive_session, e2e_id, alert_cleanup):
    body, status = Alert(thehive_session).create(
        alert_type="e2e",
        source="sadif-e2e",
        sourceRef=e2e_id,
        title=f"{e2e_id} minimal alert",
        description="**markdown** description",
    )
    assert status == 201, body
    alert_cleanup.append(body["_id"])

    stored, status = thehive_session.request(f"v1/alert/{body['_id']}")
    assert status == 200
    assert stored["type"] == "e2e"
    assert stored["source"] == "sadif-e2e"
    assert stored["sourceRef"] == e2e_id
    assert stored["title"] == f"{e2e_id} minimal alert"
    assert stored["description"] == "**markdown** description"
    # defaults do TheHive (nada opcional enviado)
    assert stored["severity"] == 2
    assert stored["tlp"] == 2
    assert stored["pap"] == 2
    assert stored["status"] == "New"


def test_alert_create_optional_fields(
    thehive_session, e2e_id, alert_cleanup, case_template, http_server
):
    link = http_server.add(f"/{e2e_id}", "<html>evidence</html>")
    body, status = Alert(thehive_session).create(
        alert_type="e2e",
        source="sadif-e2e",
        sourceRef=e2e_id,
        title=f"{e2e_id} full alert",
        description="full",
        externalLink=link,
        severity=4,
        date=1_700_000_000_000,
        tags=[e2e_id, f"{e2e_id}-phishing"],
        flag=False,
        tlp=0,  # TLP:CLEAR - era descartado por ser "falsy"
        pap=0,  # PAP:CLEAR - idem
        customFields={},  # vazio: omitido do payload
        status="New",
        caseTemplate=case_template,
    )
    assert status == 201, body
    alert_cleanup.append(body["_id"])

    stored, _ = thehive_session.request(f"v1/alert/{body['_id']}")
    assert stored["externalLink"] == link
    assert stored["severity"] == 4
    assert stored["date"] == 1_700_000_000_000
    assert sorted(stored["tags"]) == sorted([e2e_id, f"{e2e_id}-phishing"])
    assert stored["tlp"] == 0
    assert stored["pap"] == 0
    assert stored["status"] == "New"
    assert stored["caseTemplate"] == case_template
    # o TheHive não segue o link: nenhuma requisição chegou ao servidor local
    assert http_server.requests == []


def test_alert_create_v1_only_fields(thehive_session, e2e_id, alert_cleanup):
    body, status = Alert(thehive_session).create(
        alert_type="e2e",
        source="sadif-e2e",
        sourceRef=e2e_id,
        title=f"{e2e_id} v1 alert",
        description="v1",
        summary="resumo",
        assignee=SERVICE_USER,
        observables=[{"dataType": "domain", "data": f"{e2e_id}.example.org"}],
        procedures=[{"patternId": "T1566", "occurDate": 1_700_000_000_000, "description": "p"}],
    )
    assert status == 201, body
    alert_cleanup.append(body["_id"])

    stored, _ = thehive_session.request(f"v1/alert/{body['_id']}")
    assert stored.get("summary") == "resumo"
    assert stored.get("assignee") == SERVICE_USER
    observables = alert_observables(thehive_session, body["_id"])
    assert [o["data"] for o in observables] == [f"{e2e_id}.example.org"]
    procedures = query(
        thehive_session, {"_name": "getAlert", "idOrName": body["_id"]}, {"_name": "procedures"}
    )
    assert [p["patternId"] for p in procedures] == ["T1566"]


def test_alert_create_duplicate_source_ref(thehive_session, e2e_id, alert_cleanup):
    alert = Alert(thehive_session)
    kwargs = {
        "alert_type": "e2e",
        "source": "sadif-e2e",
        "sourceRef": e2e_id,
        "title": f"{e2e_id} dup",
        "description": "dup",
    }
    body, status = alert.create(**kwargs)
    assert status == 201, body
    alert_cleanup.append(body["_id"])

    body2, status2 = alert.create(**kwargs)
    assert status2 == 400
    assert body2["type"] == "CreateError"
    assert len(alerts_by_source_ref(thehive_session, e2e_id)) == 1


def test_alert_create_rejected_by_thehive(thehive_session, e2e_id, alert_cleanup):
    # passa na validação local, mas o TheHive recusa (data em formato inválido):
    # o erro volta como (corpo, status), sem exceção
    body, status = Alert(thehive_session).create(
        alert_type="e2e",
        source="sadif-e2e",
        sourceRef=e2e_id,
        title=f"{e2e_id} bad",
        description="bad",
        date="not-a-date",
    )
    if isinstance(body, dict) and body.get("_id"):
        alert_cleanup.append(body["_id"])
    assert status == 400, body
    assert body["type"] == "BadRequest"  # v1/alert valida o JSON antes de criar
    assert alerts_by_source_ref(thehive_session, e2e_id) == []


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"alert_type": ""}, "alert_type"),
        ({"alert_type": "t" * 33}, "alert_type"),
        ({"source": ""}, "source"),
        ({"source": "s" * 33}, "source"),
        ({"sourceRef": "r" * 129}, "sourceRef"),
        ({"title": ""}, "title"),
        ({"title": "t" * 513}, "title"),
        ({"description": "d" * 1_048_577}, "description"),
        ({"severity": 5}, "severity"),
        ({"severity": 0}, "severity"),
        ({"tlp": 5}, "tlp"),
        ({"pap": 4}, "pap"),
        ({"pap": True}, "pap"),
    ],
)
def test_alert_create_validation(thehive_session, e2e_id, override, fragment):
    kwargs = {
        "alert_type": "e2e",
        "source": "sadif-e2e",
        "sourceRef": e2e_id,
        "title": f"{e2e_id} invalid",
        "description": "invalid",
    }
    kwargs.update(override)
    with pytest.raises(AssertionError, match=fragment):
        Alert(thehive_session).create(**kwargs)
    # nada foi enviado ao TheHive
    assert alerts_by_source_ref(thehive_session, kwargs["sourceRef"]) == []


def test_alert_create_validation_empty_source_ref(thehive_session):
    with pytest.raises(AssertionError, match="sourceRef"):
        Alert(thehive_session).create("e2e", "sadif-e2e", "", "title", "desc")


# ---------------------------------------------------------------------- Observables


@pytest.mark.parametrize("data_type", sorted(OBSERVABLE_SAMPLES))
def test_observable_case_lifecycle_per_data_type(thehive_session, case, e2e_id, data_type):
    observable = Observable(thehive_session)
    value = sample_for(data_type, e2e_id)

    body, status = observable.add_to_case(case["_id"], data_type, value)
    assert status == 201, body
    assert len(body) == 1
    obs_id = body[0]["_id"]

    stored, status = observable.get_observable(obs_id)
    assert status == 200
    assert stored["dataType"] == data_type
    assert stored["data"] == value
    assert stored["tlp"] == 2
    assert stored["pap"] == 2
    assert stored["ioc"] is False
    assert stored["sighted"] is False
    assert [o["_id"] for o in case_observables(thehive_session, case["_id"])] == [obs_id]

    _, status = observable.update_observable(obs_id, data_type, message=f"upd {data_type}")
    assert status == 204
    assert observable.get_observable(obs_id)[0]["message"] == f"upd {data_type}"

    _, status = observable.delete_observable(obs_id)
    assert status == 204
    _, status = observable.get_observable(obs_id)
    assert status == 404
    assert case_observables(thehive_session, case["_id"]) == []


@pytest.mark.parametrize("data_type", sorted(OBSERVABLE_SAMPLES))
def test_observable_alert_per_data_type(thehive_session, raw_alert, e2e_id, data_type):
    observable = Observable(thehive_session)
    value = sample_for(data_type, e2e_id)

    body, status = observable.add_to_alert(raw_alert["_id"], data_type, value, tags=[e2e_id])
    assert status == 201, body
    obs_id = body[0]["_id"]

    stored = alert_observables(thehive_session, raw_alert["_id"])
    assert [(o["_id"], o["dataType"], o["data"]) for o in stored] == [(obs_id, data_type, value)]
    assert observable.get_observable(obs_id)[0]["tags"] == [e2e_id]

    assert observable.delete_observable(obs_id)[1] == 204
    assert alert_observables(thehive_session, raw_alert["_id"]) == []


def test_observable_add_to_case_all_fields(thehive_session, case, e2e_id):
    now = int(time.time() * 1000)
    body, status = Observable(thehive_session).add_to_case(
        case["_id"],
        "domain",
        f"{e2e_id}.evil.example",
        message="dominio malicioso",
        start_date=now - 3_600_000,
        tlp=3,
        pap=1,
        tags=[e2e_id, f"{e2e_id}-dns"],
        ioc=True,
        sighted=True,
        sighted_at=now,
        ignore_similarity=True,
    )
    assert status == 201, body
    stored = case_observables(thehive_session, case["_id"])
    assert len(stored) == 1
    obs = stored[0]
    assert obs["message"] == "dominio malicioso"
    # o TheHive 5 ignora startDate na criação e usa o instante da criação
    assert obs["startDate"] >= now - 60_000
    assert obs["tlp"] == 3
    assert obs["pap"] == 1
    assert sorted(obs["tags"]) == sorted([e2e_id, f"{e2e_id}-dns"])
    assert obs["ioc"] is True
    assert obs["sighted"] is True
    assert obs["sightedAt"] == now
    assert obs["ignoreSimilarity"] is True


def test_observable_add_to_case_duplicate(thehive_session, case, e2e_id):
    observable = Observable(thehive_session)
    value = sample_for("ip", e2e_id)
    assert observable.add_to_case(case["_id"], "ip", value)[1] == 201

    body, status = observable.add_to_case(case["_id"], "ip", value)
    assert status == 207
    assert body["success"] == []
    assert body["failure"][0]["type"] == "CreateError"
    assert len(case_observables(thehive_session, case["_id"])) == 1


def test_observable_add_to_alert_duplicate(thehive_session, raw_alert, e2e_id):
    observable = Observable(thehive_session)
    value = sample_for("url", e2e_id)
    assert observable.add_to_alert(raw_alert["_id"], "url", value)[1] == 201

    body, status = observable.add_to_alert(raw_alert["_id"], "url", value)
    assert status == 207
    assert body["failure"]
    assert len(alert_observables(thehive_session, raw_alert["_id"])) == 1


def test_observable_add_attachment_type_rejected(thehive_session, case, raw_alert):
    observable = Observable(thehive_session)
    with pytest.raises(ValueError, match="multipart"):
        observable.add_to_case(case["_id"], "file", "malware.bin")
    with pytest.raises(ValueError, match="multipart"):
        observable.add_to_alert(raw_alert["_id"], "file", "malware.bin")
    assert case_observables(thehive_session, case["_id"]) == []
    assert alert_observables(thehive_session, raw_alert["_id"]) == []


def test_observable_unknown_data_type(thehive_session, case, raw_alert, e2e_id):
    observable = Observable(thehive_session)
    body, status = observable.add_to_case(case["_id"], f"nope-{e2e_id}", "x")
    assert status == 404
    assert body["type"] == "NotFoundError"
    body, status = observable.add_to_alert(raw_alert["_id"], f"nope-{e2e_id}", "x")
    assert status == 404
    assert case_observables(thehive_session, case["_id"]) == []
    assert alert_observables(thehive_session, raw_alert["_id"]) == []


def test_observable_missing_parent(thehive_session):
    observable = Observable(thehive_session)
    _, status = observable.add_to_case(MISSING_ID, "ip", "10.0.0.1")
    assert status in (403, 404)
    _, status = observable.add_to_alert(MISSING_ID, "ip", "10.0.0.1")
    assert status in (403, 404)


def test_observable_update_fields_and_tags(thehive_session, case, e2e_id):
    observable = Observable(thehive_session)
    body, _ = observable.add_to_case(
        case["_id"], "hash", sample_for("hash", e2e_id), tags=[f"{e2e_id}a", f"{e2e_id}b"], ioc=True
    )
    obs_id = body[0]["_id"]
    now = int(time.time() * 1000)

    _, status = observable.update_observable(
        obs_id,
        "hash",
        message="atualizado",
        tlp=1,
        pap=3,
        ioc=False,
        sighted=True,
        sighted_at=now,
        ignore_similarity=True,
        add_tags=[f"{e2e_id}c"],
        remove_tags=[f"{e2e_id}a"],
    )
    assert status == 204
    stored = observable.get_observable(obs_id)[0]
    assert stored["message"] == "atualizado"
    assert stored["tlp"] == 1
    assert stored["pap"] == 3
    assert stored["ioc"] is False
    assert stored["sighted"] is True
    assert stored["sightedAt"] == now
    assert stored["ignoreSimilarity"] is True
    assert sorted(stored["tags"]) == [f"{e2e_id}b", f"{e2e_id}c"]

    # tags substitui a lista inteira
    assert observable.update_observable(obs_id, "hash", tags=[f"{e2e_id}only"])[1] == 204
    assert observable.get_observable(obs_id)[0]["tags"] == [f"{e2e_id}only"]


def test_observable_not_found(thehive_session):
    observable = Observable(thehive_session)
    assert observable.get_observable(MISSING_ID)[1] == 404
    assert observable.update_observable(MISSING_ID, "ip", message="x")[1] == 404
    assert observable.delete_observable(MISSING_ID)[1] == 404


def test_observable_delete_twice(thehive_session, case, e2e_id):
    observable = Observable(thehive_session)
    obs_id = observable.add_to_case(case["_id"], "mail", sample_for("mail", e2e_id))[0][0]["_id"]
    assert observable.delete_observable(obs_id)[1] == 204
    assert observable.delete_observable(obs_id)[1] == 404


# ---------------------------------------------------------------------------- Tasks


def test_task_create_all_fields(thehive_session, case):
    now = int(time.time() * 1000)
    body, status = Task(thehive_session).create_task_in_case(
        case["_id"],
        "Investigar dominio",
        group="triage",
        description="verificar whois",
        status="InProgress",
        flag=True,
        startDate=now,
        order=0,
        dueDate=now + 86_400_000,
        assignee=SERVICE_USER,
        mandatory=True,
    )
    assert status == 201, body
    stored, status = Task(thehive_session).get_task(body["_id"])
    assert status == 200
    assert stored["title"] == "Investigar dominio"
    assert stored["group"] == "triage"
    assert stored["description"] == "verificar whois"
    assert stored["status"] == "InProgress"
    assert stored["flag"] is True
    assert stored["startDate"] == now
    assert stored["dueDate"] == now + 86_400_000
    assert stored["assignee"] == SERVICE_USER
    assert stored["mandatory"] is True
    tasks = query(
        thehive_session, {"_name": "getCase", "idOrName": case["_id"]}, {"_name": "tasks"}
    )
    assert [t["_id"] for t in tasks] == [body["_id"]]


def test_task_create_minimal_defaults(thehive_session, case):
    body, status = Task(thehive_session).create_task_in_case(case["_id"], "Minimal")
    assert status == 201, body
    stored = Task(thehive_session).get_task(body["_id"])[0]
    assert stored["title"] == "Minimal"
    assert stored["group"] == "default"
    assert stored["status"] == "Waiting"
    assert stored["flag"] is False
    assert stored["mandatory"] is False
    assert "assignee" not in stored


def test_task_create_in_missing_case(thehive_session):
    _, status = Task(thehive_session).create_task_in_case(MISSING_ID, "orphan")
    assert status in (403, 404)


def test_task_create_invalid_status(thehive_session, case):
    body, status = Task(thehive_session).create_task_in_case(case["_id"], "bad", status="Bogus")
    # o TheHive responde 500 (NoSuchElementException) para status fora do enum
    assert status >= 400, body
    assert "Bogus" in body["message"]
    tasks = query(
        thehive_session, {"_name": "getCase", "idOrName": case["_id"]}, {"_name": "tasks"}
    )
    assert tasks == []


def test_task_update(thehive_session, case):
    task = Task(thehive_session)
    task_id = task.create_task_in_case(
        case["_id"], "Original", description="desc", flag=True, group="g1"
    )[0]["_id"]
    end = int(time.time() * 1000)

    _, status = task.update_task(
        task_id,
        title="Atualizada",
        group="g2",
        description="",  # string vazia limpa a descrição
        status="Completed",
        flag=False,
        endDate=end,
        order=0,
        assignee=SERVICE_USER,
        mandatory=True,
    )
    assert status == 204
    stored = task.get_task(task_id)[0]
    assert stored["title"] == "Atualizada"
    assert stored["group"] == "g2"
    assert stored["description"] == ""
    assert stored["status"] == "Completed"
    assert stored["flag"] is False
    assert stored["endDate"] == end
    assert stored["order"] == 0
    assert stored["assignee"] == SERVICE_USER
    assert stored["mandatory"] is True


def test_task_update_order_and_noop(thehive_session, case):
    task = Task(thehive_session)
    task_id = task.create_task_in_case(case["_id"], "Ordem")[0]["_id"]
    assert task.update_task(task_id, order=7)[1] == 204
    assert task.get_task(task_id)[0]["order"] == 7
    # order=0 também é enviado (antes era descartado por ser "falsy")
    assert task.update_task(task_id, order=0)[1] == 204
    assert task.get_task(task_id)[0]["order"] == 0
    # sem campos: no-op aceito pelo TheHive, nada muda
    assert task.update_task(task_id)[1] == 204
    assert task.get_task(task_id)[0]["title"] == "Ordem"


def test_task_update_invalid_assignee(thehive_session, case):
    task = Task(thehive_session)
    task_id = task.create_task_in_case(case["_id"], "Assign", assignee=SERVICE_USER)[0]["_id"]
    body, status = task.update_task(task_id, assignee="")
    assert status == 400, body
    assert task.get_task(task_id)[0]["assignee"] == SERVICE_USER


def test_task_actions_required(thehive_session, case):
    task = Task(thehive_session)
    task_id = task.create_task_in_case(case["_id"], "Action")[0]["_id"]
    body, status = task.get_task_actions_required(task_id)
    assert status == 200
    assert isinstance(body, dict)
    assert body
    assert all(value is False for value in body.values())


def test_task_delete_and_not_found(thehive_session, case):
    task = Task(thehive_session)
    task_id = task.create_task_in_case(case["_id"], "Apagar")[0]["_id"]
    assert task.delete_task(task_id)[1] == 204
    assert task.get_task(task_id)[1] == 404
    assert task.delete_task(task_id)[1] == 404
    assert task.update_task(task_id, title="x")[1] == 404
    tasks = query(
        thehive_session, {"_name": "getCase", "idOrName": case["_id"]}, {"_name": "tasks"}
    )
    assert tasks == []


# ------------------------------------------------------------------------- Comments


def test_comment_case_lifecycle(thehive_session, case, e2e_id):
    comment = CaseComment(thehive_session)
    body, status = comment.create_for_case(case["_id"], f"primeiro {e2e_id}")
    assert status == 201, body
    comment_id = body["_id"]
    stored = case_comments(thehive_session, case["_id"])
    assert [(c["_id"], c["message"]) for c in stored] == [(comment_id, f"primeiro {e2e_id}")]
    assert stored[0]["isEdited"] is False

    _, status = comment.update(comment_id, "editado")
    assert status in (200, 204)
    stored = case_comments(thehive_session, case["_id"])
    assert stored[0]["message"] == "editado"
    assert stored[0]["isEdited"] is True

    _, status = comment.delete(comment_id)
    assert status == 204
    assert case_comments(thehive_session, case["_id"]) == []


def test_comment_alert_lifecycle(thehive_session, raw_alert, e2e_id):
    comment = CaseComment(thehive_session)
    body, status = comment.create_for_alert(raw_alert["_id"], f"alerta {e2e_id}")
    assert status == 201, body
    steps = ({"_name": "getAlert", "idOrName": raw_alert["_id"]}, {"_name": "comments"})
    assert [c["message"] for c in query(thehive_session, *steps)] == [f"alerta {e2e_id}"]

    assert comment.update(body["_id"], "alerta editado")[1] in (200, 204)
    assert [c["message"] for c in query(thehive_session, *steps)] == ["alerta editado"]

    assert comment.delete(body["_id"])[1] == 204
    assert query(thehive_session, *steps) == []


def test_comment_invalid_and_not_found(thehive_session, case):
    comment = CaseComment(thehive_session)
    # o TheHive aceitaria um comentário vazio: a classe recusa antes de enviar
    for message in ("", "   \n"):
        with pytest.raises(ValueError, match="message"):
            comment.create_for_case(case["_id"], message)
        with pytest.raises(ValueError, match="message"):
            comment.create_for_alert(MISSING_ID, message)
    assert case_comments(thehive_session, case["_id"]) == []
    created = comment.create_for_case(case["_id"], "original")[0]
    with pytest.raises(ValueError, match="message"):
        comment.update(created["_id"], "")
    assert [c["message"] for c in case_comments(thehive_session, case["_id"])] == ["original"]
    assert comment.create_for_case(MISSING_ID, "x")[1] in (403, 404)
    assert comment.create_for_alert(MISSING_ID, "x")[1] in (403, 404)
    assert comment.update(MISSING_ID, "x")[1] == 404
    assert comment.delete(MISSING_ID)[1] == 404


# ------------------------------------------------------------------------- Markdown


def test_markdown_converter_all_types():
    content = [
        {"type": "header", "value": {"level": 3, "text": "Titulo"}},
        {"type": "paragraph", "value": "Texto livre"},
        {"type": "unordered_list", "value": ["a", "b"]},
        {"type": "ordered_list", "value": ["um", "dois"]},
        {"type": "fenced_code_block", "value": "print(1)"},
        {"type": "link", "value": {"text": "SADIF", "url": "http://127.0.0.1/x"}},
        {"type": "image", "value": {"alt_text": "logo", "url": "http://127.0.0.1/l.png"}},
        {"type": "table", "value": {"headers": ["IP", "Score"], "rows": [["10.0.0.1", 9]]}},
        {"type": "unknown", "value": "ignorado"},
        {"type": "paragraph", "value": ""},  # vazio: ignorado
        {"value": "sem tipo"},
    ]
    expected = [
        "### Titulo",
        "Texto livre",
        "- a\n- b",
        "1. um\n2. dois",
        "```\nprint(1)\n```",
        "[SADIF](http://127.0.0.1/x)",
        "![logo](http://127.0.0.1/l.png)",
        "| IP | Score |\n| --- | --- |\n| 10.0.0.1 | 9 |",
    ]
    assert MarkdownConverter().convert(content) == "\n".join(expected)


def test_markdown_converter_defaults_and_custom_bullet():
    converter = MarkdownConverter(unordered_list_char="*")
    assert converter.convert_unordered_list(["x", "y"]) == "* x\n* y"
    assert converter.convert_header({}) == "# "
    assert converter.convert_link({}) == "[]()"
    assert converter.convert_image({}) == "![]()"
    assert converter.convert_table({}) == "|  |\n|  |"
    assert converter.convert([]) == ""


def test_markdown_posted_as_case_comment(thehive_session, case, e2e_id):
    markdown = MarkdownConverter().convert(
        [
            {"type": "header", "value": {"level": 2, "text": f"Relatorio {e2e_id}"}},
            {"type": "table", "value": {"headers": ["k", "v"], "rows": [["ip", "10.0.0.1"]]}},
            {"type": "fenced_code_block", "value": "rule x { condition: true }"},
        ]
    )
    body, status = CaseComment(thehive_session).create_for_case(case["_id"], markdown)
    assert status == 201, body
    assert [c["message"] for c in case_comments(thehive_session, case["_id"])] == [markdown]


# ------------------------------------------------------------------------ Templates

TEMPLATES = sorted(
    name
    for name, value in vars(CaseCommentTemplate).items()
    if name.isupper() and isinstance(value, list)
)


def template_placeholders(template):
    texts = []
    for item in template:
        value = item["value"]
        if isinstance(value, dict):
            texts.append(value.get("text", ""))
        elif isinstance(value, list):
            texts.extend(value)
        else:
            texts.append(value)
    return {field for text in texts for _, field, _, _ in string.Formatter().parse(text) if field}


def test_templates_discovered():
    assert {"MALICIOUS_DNS_ALERT", "CASE_MONITORING_DNS_ALERT_YARA"} <= set(TEMPLATES)


@pytest.mark.parametrize("name", TEMPLATES)
def test_template_render_and_post(thehive_session, case, e2e_id, name):
    template = getattr(CaseCommentTemplate, name)
    placeholders = template_placeholders(template)
    assert placeholders
    values = {field: f"{field}-{e2e_id}" for field in placeholders}

    rendered = TemplateRenderer(template, **values, extra_ignored="x").render()
    assert "{" not in rendered
    assert "}" not in rendered
    for value in values.values():
        assert value in rendered
    assert "extra_ignored" not in rendered
    # cada bloco vira um trecho separado por linha em branco
    assert rendered.count("\n\n") == len(template) - 1
    first = template[0]["value"]
    assert rendered.startswith("#" * first["level"] + " " + first["text"])

    body, status = CaseComment(thehive_session).create_for_case(case["_id"], rendered)
    assert status == 201, body
    assert [c["message"] for c in case_comments(thehive_session, case["_id"])] == [rendered]


def test_template_render_malicious_dns_exact():
    rendered = TemplateRenderer(
        CaseCommentTemplate.MALICIOUS_DNS_ALERT,
        dominio_suspeito="evil.example",
        ip_associado="10.0.0.1",
        data_registro="2024-01-01",
        data_atualizacao="2024-02-01",
    ).render()
    assert rendered == (
        "# Alerta de DNS Malicioso\n\n"
        "## Domínio Suspeito: evil.example\n\n"
        "- IP associado: 10.0.0.1\n"
        "- Registrado em: 2024-01-01\n"
        "- Atualizado em: 2024-02-01"
    )


@pytest.mark.parametrize("name", TEMPLATES)
def test_template_missing_placeholder(thehive_session, case, name):
    template = getattr(CaseCommentTemplate, name)
    placeholders = sorted(template_placeholders(template))
    missing = placeholders[0]
    values = {field: "v" for field in placeholders[1:]}
    with pytest.raises(KeyError, match=missing):
        TemplateRenderer(template, **values).render()
    # nada é comentado quando a renderização falha
    assert case_comments(thehive_session, case["_id"]) == []


def test_template_renderer_extra_block_types():
    template = [
        {"type": "header", "value": {"text": "Caso {n}"}},
        {"type": "ordered_list", "value": ["passo {n}", "fim"]},
        {"type": "table", "value": {"headers": ["campo"], "rows": [["{n}"]]}},
        {"type": "link", "value": {"text": "ver {n}", "url": "http://127.0.0.1/{n}"}},
        {"type": "desconhecido", "value": "ignorado"},
    ]
    assert TemplateRenderer(template, n="42").render() == (
        "# Caso 42\n\n"
        "1. passo 42\n2. fim\n\n"
        "| campo |\n| --- |\n| 42 |\n\n"
        "[ver 42](http://127.0.0.1/42)"
    )
    assert TemplateRenderer([]).render() == ""


# ---------------------------------------------------------- logs (fixes verificados)


def _records(caplog, category):
    return [r.getMessage() for r in caplog.records if r.name == category]


def test_alert_create_logs_follow_http_status(thehive_session, e2e_id, alert_cleanup, caplog):
    caplog.set_level("DEBUG")
    alert = Alert(thehive_session)
    kwargs = {
        "alert_type": "e2e",
        "source": "sadif-e2e",
        "sourceRef": e2e_id,
        "title": f"{e2e_id} log",
        "description": "log",
    }
    body, status = alert.create(**kwargs)
    assert status == 201, body
    alert_cleanup.append(body["_id"])
    assert _records(caplog, "thehive_alert_creation") == [
        f"[SUCCESS] - Alert created successfully in TheHive: {e2e_id}"
    ]

    caplog.clear()
    _, status = alert.create(**kwargs)  # duplicado: 400
    assert status == 400
    messages = _records(caplog, "thehive_alert_creation")
    assert len(messages) == 1
    assert messages[0].startswith(f"[FAILED] - TheHive did not create the alert {e2e_id}")

    caplog.clear()
    with pytest.raises(AssertionError):
        alert.create(**{**kwargs, "severity": 9})
    assert _records(caplog, "thehive_alert_creation") == []
    assert len(_records(caplog, "thehive_alert_validation")) == 1
    assert len(alerts_by_source_ref(thehive_session, e2e_id)) == 1


def test_observable_add_to_alert_logs(thehive_session, raw_alert, e2e_id, caplog):
    caplog.set_level("DEBUG")
    observable = Observable(thehive_session)
    value = sample_for("domain", e2e_id)
    assert observable.add_to_alert(raw_alert["_id"], "domain", value)[1] == 201
    assert _records(caplog, "observable_add") == [
        f"[SUCCESS] - Observable added to alert {raw_alert['_id']} successfully."
    ]
    caplog.clear()
    assert observable.add_to_alert(raw_alert["_id"], "domain", value)[1] == 207
    messages = _records(caplog, "observable_add")
    assert len(messages) == 1
    assert messages[0].startswith(
        f"[FAILED] - Failed to add observable to alert {raw_alert['_id']}"
    )
    assert len(alert_observables(thehive_session, raw_alert["_id"])) == 1


def test_task_create_order_is_assigned_by_thehive(thehive_session, case):
    # O TheHive 5 (v0 e v1) ignora "order" na criação e atribui a posição sozinho;
    # o valor só é gravado via update_task. mandatory só é gravado pela API v1.
    task = Task(thehive_session)
    task_id = task.create_task_in_case(case["_id"], "Ordem 5", order=5, mandatory=True)[0]["_id"]
    stored = task.get_task(task_id)[0]
    assert stored["mandatory"] is True
    assert stored["order"] != 5
    assert task.update_task(task_id, order=5)[1] == 204
    assert task.get_task(task_id)[0]["order"] == 5
