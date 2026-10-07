import pytest

pytestmark = pytest.mark.e2e

import os  # noqa: E402

import requests  # noqa: E402
from typeguard import TypeCheckError  # noqa: E402

from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.caso_de_uso.caselist import (  # noqa: E402
    CaseLister,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_datatype import (  # noqa: E402
    CaseDataType,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.case_response import (  # noqa: E402
    CaseResponse,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.create_case import (  # noqa: E402
    CreateCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.delete_case import (  # noqa: E402
    DeleteCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.get_case import (  # noqa: E402
    GetCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.list_case import (  # noqa: E402
    ListCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.save_case import (  # noqa: E402
    MongoDBSaver,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case.update_case import (  # noqa: E402
    UpdateCase,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_session import (  # noqa: E402
    SessionThehive,
)

THEHIVE_URL = os.environ.get("SADIF_THEHIVE", "http://localhost:9000/api")
ORGANISATION = "SADIF"


def _find_by_title(session: SessionThehive, title: str) -> list[dict]:
    query = {
        "query": [
            {"_name": "listCase"},
            {"_name": "filter", "_eq": {"_field": "title", "_value": title}},
        ]
    }
    response, status = session.request("v1/query", method="POST", json_data=query)
    assert status == 200, response
    return [case for case in response if case["title"] == title]


@pytest.fixture()
def cases(thehive_session, e2e_id):
    """Cria casos via CreateCase e apaga ao final todos os casos com o e2e_id no título."""
    creator = CreateCase(thehive_session)
    created: list[str] = []

    def make(suffix: str = "", **fields) -> dict:
        data = CaseDataType(
            title=f"{e2e_id} {suffix}".strip(),
            description=fields.pop("description", f"descricao {e2e_id}"),
            tags=fields.pop("tags", [e2e_id]),
            **fields,
        )
        response, status = creator.create(data)
        assert status == 201, response
        created.append(response["_id"])
        return response

    make.created = created
    yield make
    query = {
        "query": [
            {"_name": "listCase"},
            {"_name": "filter", "_like": {"_field": "title", "_value": f"*{e2e_id}*"}},
        ]
    }
    leftovers, _ = thehive_session.request("v1/query", method="POST", json_data=query)
    ids = set(created) | {c["_id"] for c in leftovers if isinstance(leftovers, list)}
    for case_id in ids:
        thehive_session.request(f"v1/case/{case_id}", method="DELETE")


# ----------------------------------------------------------------- SessionThehive


def test_session_api_key_status_and_current_user(thehive_session):
    body, status = thehive_session.get_status()
    assert status == 200
    assert "TheHive" in body["versions"]

    user, status = thehive_session.request("v1/user/current")
    assert status == 200
    assert user["organisation"] == ORGANISATION
    assert thehive_session.headers["Authorization"].startswith("Bearer ")


def test_session_default_base_url_with_trailing_slash_works(thehive_session):
    session = SessionThehive(base_url=THEHIVE_URL.rstrip("/") + "/")
    session.set_api_key(thehive_session.headers["Authorization"].removeprefix("Bearer "))
    body, status = session.request("/status")
    assert status == 200, body
    assert SessionThehive().base_url == "http://localhost:9000/api/"


def test_session_basic_auth_admin_and_wrong_password():
    session = SessionThehive(base_url=THEHIVE_URL)
    session.set_basic_auth("admin@thehive.local", "secret")
    user, status = session.request("v1/user/current")
    assert status == 200, user
    assert user["login"] == "admin@thehive.local"
    assert "Authorization" not in session.headers

    session.set_basic_auth("admin@thehive.local", "wrong-password")
    body, status = session.request("v1/user/current")
    assert status == 401
    assert body["type"] == "AuthenticationError"


def test_session_cookie_from_login(thehive_session):
    login = requests.post(
        f"{THEHIVE_URL}/v1/login",
        json={"user": "admin@thehive.local", "password": "secret"},
        timeout=30,
    )
    assert login.ok
    session = SessionThehive(base_url=THEHIVE_URL)
    session.set_basic_auth("x", "y")
    session.set_session(login.cookies["THEHIVE-SESSION"])
    assert session.auth is None
    user, status = session.request("v1/user/current")
    assert status == 200, user
    assert user["login"] == "admin@thehive.local"


def test_session_api_key_resets_previous_auth(thehive_session):
    key = thehive_session.headers["Authorization"].removeprefix("Bearer ")
    session = SessionThehive(base_url=THEHIVE_URL)
    session.set_session("bogus")
    session.set_api_key(key)
    assert session.cookies == {}
    _, status = session.request("v1/user/current")
    assert status == 200


def test_session_invalid_api_key_returns_401():
    session = SessionThehive(base_url=THEHIVE_URL)
    session.set_api_key("invalid-key")
    body, status = session.request("case")
    assert status == 401
    assert body["type"] == "AuthenticationError"


def test_session_organisation_header(thehive_session):
    thehive_session.set_organisation(ORGANISATION)
    assert thehive_session.headers["X-Organisation"] == ORGANISATION
    body, status = thehive_session.request("v1/user/current")
    assert status == 200
    assert body["organisation"] == ORGANISATION

    thehive_session.set_organisation("org-that-does-not-exist")
    _, status = thehive_session.request("case")
    assert status in (401, 403, 404)


def test_session_not_found_and_non_json_and_network_error(thehive_session):
    body, status = thehive_session.request("v1/case/~999999999")
    assert status == 404
    assert body["type"] == "NotFoundError"

    body, status = thehive_session.request("endpoint-that-does-not-exist")
    assert status == 404

    offline = SessionThehive(base_url="http://127.0.0.1:1/api")
    body, status = offline.request("status")
    assert status == 0
    assert isinstance(body, str)
    assert body


def test_session_create_alert_validation_error(thehive_session, e2e_id):
    # payload incompleto: o TheHive recusa com 400 e o corpo de erro é devolvido
    body, status = thehive_session.create_alert({"title": f"{e2e_id} alerta"})
    assert status == 400
    assert isinstance(body, dict)
    assert body.get("type")


def test_session_create_alert_success(thehive_session, e2e_id):
    body, status = thehive_session.create_alert(
        {
            "type": "e2e",
            "source": "sadif-e2e",
            "sourceRef": e2e_id,
            "title": f"{e2e_id} alerta",
            "description": "alerta e2e",
        }
    )
    assert status == 201, body
    try:
        found, _ = thehive_session.request(f"v1/alert/{body['_id']}")
        assert found["sourceRef"] == e2e_id
    finally:
        thehive_session.request(f"v1/alert/{body['_id']}", method="DELETE")


# ----------------------------------------------------------------------- CreateCase


def test_create_case_rejects_non_session():
    with pytest.raises((TypeCheckError, ValueError)):
        CreateCase(session="not a session")


def test_create_case_minimal_defaults(thehive_session, cases, e2e_id):
    created = cases("minimal")
    stored, status = GetCase(thehive_session).fetch_case(created["_id"])
    assert status == 200
    assert stored["title"] == f"{e2e_id} minimal"
    assert stored["severity"] == 2
    assert stored["tlp"] == 2
    assert stored["pap"] == 2
    assert stored["tags"] == [e2e_id]
    # startDate=0 do dataclass não deve virar 1970: o TheHive usa a data atual
    assert stored["startDate"] > 1_600_000_000_000
    assert stored["assignee"] == "sadif@thehive.local"


def test_create_case_all_optional_fields(thehive_session, cases, e2e_id):
    created = cases(
        "full",
        description="**markdown** completo",
        severity=4,
        tlp=3,
        pap=1,
        flag=True,
        tags=[e2e_id, "phishing"],
        summary="resumo e2e",
        startDate=1_700_000_000_000,
        endDate=1_800_000_000_000,
        owner="sadif@thehive.local",
        stats={
            "tasks": [{"title": f"task {e2e_id}"}],
            "sharingParameters": [{"organisation": ORGANISATION}],
        },
    )
    stored, status = GetCase(thehive_session).fetch_case(created["_id"])
    assert status == 200
    assert stored["description"] == "**markdown** completo"
    assert stored["severity"] == 4
    # API v0 (POST /api/case) usa TLP 0-3; a v1 tem AMBER+STRICT, então compara os rótulos
    assert stored["tlpLabel"] == "RED"
    assert stored["papLabel"] == "GREEN"
    assert stored["flag"] is True
    assert set(stored["tags"]) == {e2e_id, "phishing"}
    assert stored["summary"] == "resumo e2e"
    assert stored["startDate"] == 1_700_000_000_000
    assert stored["endDate"] == 1_800_000_000_000
    assert stored["assignee"] == "sadif@thehive.local"

    query = {"query": [{"_name": "getCase", "idOrName": created["_id"]}, {"_name": "tasks"}]}
    tasks, status = thehive_session.request("v1/query", method="POST", json_data=query)
    assert status == 200
    assert [t["title"] for t in tasks] == [f"task {e2e_id}"]


def test_create_case_duplicate_title_not_created(thehive_session, cases, e2e_id):
    cases("dup")
    # cria >10 casos para o original sair da primeira página do GET /api/case
    for i in range(11):
        cases(f"filler{i}")
    result = CreateCase(thehive_session).create(
        CaseDataType(title=f"{e2e_id} dup", description="x", tags=[e2e_id])
    )
    assert result == "A case with the same title already exists"
    assert len(_find_by_title(thehive_session, f"{e2e_id} dup")) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", ""),
        ("title", "x" * 513),
        ("severity", 5),
        ("severity", 0),
        ("tlp", 4),
        ("tlp", 5),
        ("pap", 4),
        ("status", ""),
        ("status", "s" * 65),
    ],
)
def test_create_case_validation_errors(thehive_session, e2e_id, field, value):
    data = CaseDataType(title=f"{e2e_id} invalid", description="x", tags=[e2e_id])
    setattr(data, field, value)
    with pytest.raises(ValueError, match=field):
        CreateCase(thehive_session).create(data)
    assert _find_by_title(thehive_session, f"{e2e_id} invalid") == []


def test_create_case_unauthenticated_returns_error_status(e2e_id):
    session = SessionThehive(base_url=THEHIVE_URL)
    session.set_api_key("invalid-key")
    response, status = CreateCase(session).create(
        CaseDataType(title=f"{e2e_id} noauth", description="x")
    )
    assert status == 401
    assert response["type"] == "AuthenticationError"


# ----------------------------------------------------------- Get / List / Update / Delete


def test_get_case_by_id_and_number_and_not_found(thehive_session, cases, e2e_id):
    created = cases("get")
    getter = GetCase(thehive_session)
    by_id, status = getter.fetch_case(created["_id"])
    assert status == 200
    assert by_id["title"] == f"{e2e_id} get"
    by_number, status = getter.fetch_case(str(by_id["number"]))
    assert status == 200
    assert by_number["_id"] == created["_id"]

    body, status = getter.fetch_case("~999999999")
    assert status == 404
    assert body["type"] == "NotFoundError"


def test_list_case_default_page_and_all(thehive_session, cases, e2e_id):
    for i in range(11):
        cases(f"list{i}")
    lister = ListCase(thehive_session)
    page, status = lister.list_cases()
    assert status == 200
    assert len(page) == 10
    everything, status = lister.list_cases(case_range="all")
    assert status == 200
    titles = {c["title"] for c in everything}
    assert {f"{e2e_id} list{i}" for i in range(11)} <= titles

    bad = SessionThehive(base_url=THEHIVE_URL)
    bad.set_api_key("invalid-key")
    body, status = ListCase(bad).list_cases()
    assert status == 401


def test_update_case_success_and_not_found(thehive_session, cases, e2e_id):
    created = cases("upd")
    updater = UpdateCase(thehive_session)
    body, status = updater.update_case(
        created["_id"],
        {"title": f"{e2e_id} upd2", "severity": 3, "tags": [e2e_id, "updated"], "flag": True},
    )
    assert status == 200, body
    stored, _ = GetCase(thehive_session).fetch_case(created["_id"])
    assert stored["title"] == f"{e2e_id} upd2"
    assert stored["severity"] == 3
    assert set(stored["tags"]) == {e2e_id, "updated"}
    assert stored["flag"] is True

    body, status = updater.update_case("~999999999", {"title": "x"})
    assert status == 404

    body, status = updater.update_case(created["_id"], {"severity": "not-a-number"})
    assert status == 400
    stored, _ = GetCase(thehive_session).fetch_case(created["_id"])
    assert stored["severity"] == 3


def test_delete_case_and_not_found(thehive_session, cases):
    created = cases("del")
    deleter = DeleteCase(thehive_session)
    body, status = deleter.delete_case(created["_id"])
    assert status == 204
    _, status = GetCase(thehive_session).fetch_case(created["_id"])
    assert status == 404

    body, status = deleter.delete_case(created["_id"])
    assert status == 404
    assert body["type"] == "NotFoundError"


# --------------------------------------------------------------------- CaseResponse


def test_case_response_from_real_case(thehive_session, cases, e2e_id):
    created = cases("resp", severity=3)
    body, status = GetCase(thehive_session).fetch_case(created["_id"])
    response = CaseResponse(status, body)
    assert response.is_success()
    assert response._id == created["_id"]
    assert response.title == f"{e2e_id} resp"
    assert response.severity == 3
    assert response.severityLabel == "HIGH"
    assert response.tags == [e2e_id]
    assert response.number == body["number"]
    assert str(response) == f"Case: {e2e_id} resp - descricao {e2e_id}"


def test_case_response_created_status_is_success(thehive_session, e2e_id, cases):
    response, status = CreateCase(thehive_session).create(
        CaseDataType(title=f"{e2e_id} resp201", description="d", tags=[e2e_id])
    )
    cases.created.append(response["_id"])
    assert status == 201
    case_response = CaseResponse(status, response)
    assert case_response.is_success()
    assert case_response.title == f"{e2e_id} resp201"


def test_case_response_errors(thehive_session):
    body, status = GetCase(thehive_session).fetch_case("~999999999")
    response = CaseResponse(status, body)
    assert not response.is_success()
    assert response.error_type == "NotFoundError"
    assert response.error_message == "Case not found"
    assert str(response) == "Error (404): NotFoundError - Case not found"

    deleted_ok = CaseResponse(204, "")
    assert deleted_ok.is_success()
    assert deleted_ok.title is None

    offline = CaseResponse(0, "connection refused")
    assert not offline.is_success()
    assert offline.error_message == "connection refused"


# --------------------------------------------------------------------- MongoDBSaver


def test_mongodb_saver_saves_and_upserts_cases(
    sadif_databases, mongo_client, thehive_session, cases, e2e_id
):
    cases("save1")
    cases("save2")
    found = CaseLister(thehive_session).list_cases_by_tag(e2e_id)
    assert len(found) == 2

    db_name = sadif_databases["MONGODB_DATABASE_CLIENTS"]
    saver = MongoDBSaver(None, db_name, "thehive_cases", db_client=mongo_client)
    assert saver.save_cases(found) == 2
    assert all("_id" in c and isinstance(c["_id"], str) for c in found)
    collection = mongo_client[db_name]["thehive_cases"]
    stored = {d["_id"]: d for d in collection.find()}
    assert set(stored) == {c["_id"] for c in found}
    assert {d["title"] for d in stored.values()} == {f"{e2e_id} save1", f"{e2e_id} save2"}

    # salvar de novo atualiza em vez de duplicar / falhar
    found[0]["title"] = "changed"
    assert saver.save_cases(found) == 2
    assert collection.count_documents({}) == 2
    assert collection.find_one({"_id": found[0]["_id"]})["title"] == "changed"

    # documentos sem _id recebem um ObjectId sem alterar o dict do chamador
    loose = {"title": "sem id"}
    assert saver.save_cases([loose]) == 1
    assert "_id" not in loose
    assert collection.count_documents({"title": "sem id"}) == 1

    assert saver.save_cases([]) == 0
    with pytest.raises((TypeError, TypeCheckError)):
        saver.save_cases(["not a dict"])


def test_mongodb_saver_with_uri(sadif_databases, mongo_client, e2e_id):
    db_name = sadif_databases["MONGODB_DATABASE_CLIENTS"]
    saver = MongoDBSaver(os.environ["SADIF_MONGODB_URL"], db_name, "cases")
    try:
        saver.save_cases([{"_id": f"~{e2e_id}", "title": e2e_id}])
    finally:
        saver.mongo_client.close()
    assert mongo_client[db_name]["cases"].find_one({"_id": f"~{e2e_id}"})["title"] == e2e_id

    with pytest.raises(ValueError):
        MongoDBSaver(None, db_name, "cases")


# ----------------------------------------------------------------------- CaseLister


def test_case_lister_lists_all_pages_and_filters_by_tag(thehive_session, cases, e2e_id):
    for i in range(11):
        cases(f"lister{i}", tags=[e2e_id, f"{e2e_id}-even" if i % 2 == 0 else "odd"])
    lister = CaseLister(thehive_session)
    all_cases = lister.list_cases()
    titles = {c["title"] for c in all_cases}
    assert {f"{e2e_id} lister{i}" for i in range(11)} <= titles

    tagged = lister.list_cases_by_tag(f"{e2e_id}-even")
    assert sorted(c["title"] for c in tagged) == sorted(
        f"{e2e_id} lister{i}" for i in range(0, 11, 2)
    )
    assert len(lister.list_cases_by_tag(e2e_id)) == 11
    assert lister.list_cases_by_tag(f"{e2e_id}-missing") == []


def test_case_lister_raises_on_auth_error():
    session = SessionThehive(base_url=THEHIVE_URL)
    session.set_api_key("invalid-key")
    lister = CaseLister(session)
    with pytest.raises(Exception, match="Status 401"):
        lister.list_cases()
    with pytest.raises(Exception, match="Status 401"):
        lister.list_cases_by_tag("x")


# ------------------------------------------------------------- extra edge cases


def test_create_case_tlp_pap_boundaries(thehive_session, cases, e2e_id):
    created = cases("white", tlp=0, pap=0, severity=1)
    stored, status = GetCase(thehive_session).fetch_case(created["_id"])
    assert status == 200
    assert stored["tlp"] == 0
    assert stored["tlpLabel"] in ("WHITE", "CLEAR")
    assert stored["pap"] == 0
    assert stored["severity"] == 1


def test_case_managers_network_error_status_zero(e2e_id):
    offline = SessionThehive(base_url="http://127.0.0.1:1/api")
    offline.timeout = 5

    body, status = GetCase(offline).fetch_case("~1")
    assert status == 0
    assert isinstance(body, str)

    body, status = ListCase(offline).list_cases(case_range="all")
    assert status == 0

    response, status = CreateCase(offline).create(
        CaseDataType(title=f"{e2e_id} offline", description="x")
    )
    assert status == 0
    assert isinstance(response, str)
    assert not CaseResponse(status, response).is_success()

    with pytest.raises(Exception, match="Status 0"):
        CaseLister(offline).list_cases()


def test_case_response_from_real_delete(thehive_session, cases):
    created = cases("resp204")
    body, status = DeleteCase(thehive_session).delete_case(created["_id"])
    response = CaseResponse(status, body)
    assert status == 204
    assert response.is_success()
    assert response._id is None
