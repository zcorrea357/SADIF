import pytest

pytestmark = pytest.mark.e2e

# Pipeline completo do SADIF, de ponta a ponta e contra a infraestrutura real:
# repositório git de clientes -> ClientManagerImport -> repositório git de regras YARA ->
# YaraRulesImporter -> repositório git de alvos do crawler -> CrawlerManagerImporter ->
# BaseCrawler (páginas servidas pelo http_server local) -> um caso no TheHive por match
# (CaseCommentTemplate + TemplateRenderer + CreateCase) -> GetCase/ListCase/CaseLister ->
# WebhookSender -> limpeza (DeleteCase).

import base64  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from sadif.clientmanager.client_data_import import ClientManagerImport  # noqa: E402
from sadif.clientmanager.client_data_manager import ClientManager  # noqa: E402
from sadif.frameworks_drivers.crawler.base_crawler import BaseCrawler  # noqa: E402
from sadif.frameworks_drivers.crawler.crawler_data_import import (  # noqa: E402
    CrawlerManagerImporter,
)
from sadif.frameworks_drivers.gitmanager import GitManager  # noqa: E402
from sadif.frameworks_drivers.notification.webhook import WebhookSender  # noqa: E402
from sadif.frameworks_drivers.sadif_yara.yara_import import YaraRulesImporter  # noqa: E402
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.caso_de_uso.caselist import (  # noqa: E402
    CaseLister,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_datatype import (  # noqa: E402
    CaseDataType,
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
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case_comment_template import (  # noqa: E402
    CaseCommentTemplate,
)
from sadif.frameworks_drivers.ticket_system.thehive.thehive_internal_mods_api.thehive_manager_case_comment_template.template_render import (  # noqa: E402
    TemplateRenderer,
)

YARA_RULE = """rule {name}
{{
    meta:
        description = "pipeline e2e"
    strings:
        $s = "{needle}"
    condition:
        $s
}}
"""


def _rule(name: str, needle: str) -> str:
    return YARA_RULE.format(name=name, needle=needle)


@pytest.fixture()
def git_managers():
    """GitManagers criados no teste; o diretório temporário de cada um é removido ao final."""
    managers: list[GitManager] = []

    def make(url: str) -> GitManager:
        manager = GitManager(url)
        managers.append(manager)
        return manager

    yield make
    for manager in managers:
        manager.cleanup()
        assert not Path(manager.repo_dir).exists()


@pytest.fixture()
def created_cases(thehive_session):
    """Ids dos casos criados no TheHive; todos são apagados ao final do teste."""
    ids: list[str] = []
    yield ids
    deleter = DeleteCase(thehive_session)
    for case_id in ids:
        deleter.delete_case(case_id)
    for case_id in ids:
        _, status = GetCase(thehive_session).fetch_case(case_id)
        assert status == 404


@pytest.fixture()
def pipeline_env(sadif_databases, mongo_client, thehive_session, e2e_id, http_server):
    """Clientes, nomes e páginas usados pelo pipeline."""
    alpha = f"Alpha{e2e_id}"
    beta = f"Beta{e2e_id}"
    gamma = f"Gamma{e2e_id}"  # cliente sem nenhuma página com match
    secrets = {
        "alpha_leak": f"alpha-leak-{e2e_id}",
        "alpha_vips": f"alpha-vip-{e2e_id}",
        "beta_leak": f"beta-leak-{e2e_id}",
        "orphan": f"orphan-{e2e_id}",
        "gamma": f"gamma-never-{e2e_id}",
    }
    base = f"/{e2e_id}"
    pages = {
        # site público: index -> leak (alpha e beta) e vips (alpha), um link quebrado
        "index": http_server.add(
            f"{base}/index.html",
            '<html><body><a href="leak.html">leak</a> <a href="vips.html#top">vips</a>'
            ' <a href="missing.html">missing</a> <a href="mailto:x@example.com">mail</a>'
            " nada aqui</body></html>",
        ),
        "leak": http_server.add(
            f"{base}/leak.html",
            f"<html><body>dump: {secrets['alpha_leak']} e {secrets['beta_leak']}"
            f" e {secrets['orphan']}</body></html>",
        ),
        "vips": http_server.add(
            f"{base}/vips.html",
            f"<html><body>lista vip {secrets['alpha_vips']} {secrets['alpha_vips']}</body></html>",
        ),
        "missing": f"{http_server.url}{base}/missing.html",
        # site com credencial: o crawler deve enviar o header Authorization
        "portal": http_server.add(
            f"{base}/portal.html",
            f"<html><body>portal interno {secrets['beta_leak']}</body></html>",
        ),
        # alvo fora do ar (404)
        "down": http_server.add(f"{base}/down.html", "gone", status=404),
    }
    return {
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "secrets": secrets,
        "pages": pages,
        "db": sadif_databases,
    }


def _import_clients(mongo_client, local_git_repo, git_managers, env) -> list[str]:
    clients = {
        env["alpha"]: {"client_name": env["alpha"], "company": "Alpha SA", "ciid": "CI-A"},
        env["beta"]: {"client_name": env["beta"], "company": "Beta Ltda", "ciid": "CI-B"},
        env["gamma"]: {"client_name": env["gamma"], "company": "Gamma ME", "ciid": "CI-G"},
    }
    repo = local_git_repo(
        {f"clients/Client_{name}.json": json.dumps(document) for name, document in clients.items()}
        | {"README.md": "clientes monitorados"}
    )
    importer = ClientManagerImport(db_client=mongo_client, git_manager=git_managers(repo))
    result = importer.import_from_json()
    assert result == "JSON data import to MongoDB completed successfully."

    clients_db = mongo_client[env["db"]["MONGODB_DATABASE_CLIENTS"]]
    for name, document in clients.items():
        stored = clients_db[f"Client_{name}"].find_one({}, {"_id": 0})
        assert stored == document
    registered = ClientManager(mongo_client).list_all_clients()
    assert registered == sorted(clients)
    return registered


def _import_rules(mongo_client, local_git_repo, git_managers, env, clients) -> dict:
    alpha, beta, secrets = env["alpha"], env["beta"], env["secrets"]
    rules = {
        f"{alpha}MonitoramentoLeak01": (alpha, "Leak", secrets["alpha_leak"]),
        f"{alpha}MonitoramentoVips01": (alpha, "Vips", secrets["alpha_vips"]),
        f"{beta}MonitoramentoLeak01": (beta, "Leak", secrets["beta_leak"]),
        f"{env['gamma']}MonitoramentoPOC01": (env["gamma"], "POC", secrets["gamma"]),
    }
    files = {
        f"{client}/{name}.yar": _rule(name, needle) for name, (client, _, needle) in rules.items()
    }
    # cliente não cadastrado, YARA inválido e arquivo sem regra: nunca chegam ao banco
    files["other/UnknownMonitoramentoLeak01.yar"] = _rule(
        "UnknownMonitoramentoLeak01", secrets["orphan"]
    )
    files[f"{alpha}/{alpha}MonitoramentoLeak99.yar"] = (
        f"rule {alpha}MonitoramentoLeak99 {{ condition: $missing }}"
    )
    files["notes/empty.yara"] = "// nenhuma regra aqui\n"
    files["notes/readme.txt"] = "ignorado"
    repo = local_git_repo(files)

    importer = YaraRulesImporter(
        None, clients, db_client=mongo_client, git_manager=git_managers(repo)
    )
    summary = importer.import_rules()
    assert summary["imported"] == len(rules)
    assert summary["duplicated_rules"] == []
    assert summary["invalid_rules"] == [f"{alpha}MonitoramentoLeak99.yar"]
    assert sorted(summary["ignored_rules"]) == sorted(
        ["UnknownMonitoramentoLeak01.yar", f"{alpha}MonitoramentoLeak99.yar", "empty.yara"]
    )

    yara_db = mongo_client[env["db"]["MONGODB_DATABASE_YARA"]]
    assert sorted(yara_db.list_collection_names()) == sorted(
        f"Client_{c}" for c in (alpha, beta, env["gamma"])
    )
    for name, (client, rule_type, _) in rules.items():
        stored = yara_db[f"Client_{client}"].find_one({"rule_name": name}, {"_id": 0})
        assert stored == {
            "rule_name": name,
            "rule_content": files[f"{client}/{name}.yar"],
            "rule_type": rule_type,
            "client": client,
        }
    return rules


def _import_targets(mongo_client, local_git_repo, git_managers, env) -> dict[str, list[dict]]:
    pages = env["pages"]
    repo = local_git_repo(
        {
            "crawler_without_credential_web/public.json": json.dumps(
                [{"url": pages["index"], "depth": 1}, {"url": pages["down"], "depth": 0}]
            ),
            "crawler_with_credential_web/portal.json": json.dumps(
                {
                    "url": pages["portal"],
                    "depth": 0,
                    "credentials": {"username": "analyst", "password": "s3cret"},
                }
            ),
            "crawler_without_credential_web/broken.json": "{not json",
            "crawler_without_credential_web/nourl.json": json.dumps({"depth": 1}),
            "docs/ignored.json": json.dumps({"url": "http://127.0.0.1:1/ignored"}),
        }
    )
    importer = CrawlerManagerImporter(db_client=mongo_client, git_manager=git_managers(repo))
    result = importer.import_collections()
    assert result is not None
    assert sorted(result["imported"]) == sorted([pages["index"], pages["down"], pages["portal"]])
    assert sorted(name for name, _ in result["ignored"]) == ["broken.json", "nourl.json"]

    crawler_db = mongo_client[env["db"]["MONGODB_DATABASE_CRAWLER"]]
    targets = {
        name: list(crawler_db[name].find({}, {"_id": 0}).sort("url"))
        for name in ("crawler_without_credential_web", "crawler_with_credential_web")
    }
    assert [t["url"] for t in targets["crawler_without_credential_web"]] == sorted(
        [pages["index"], pages["down"]]
    )
    assert targets["crawler_with_credential_web"][0]["credentials"]["username"] == "analyst"
    assert "ignored" not in crawler_db.list_collection_names()
    return targets


def _crawl(mongo_client, targets) -> tuple[list[dict], list[BaseCrawler]]:
    matches = []
    crawlers = []
    for collection_name, documents in sorted(targets.items()):
        for target in documents:
            crawler = BaseCrawler(target["url"], depth=target["depth"], db_client=mongo_client)
            if collection_name.startswith("crawler_with_credential"):
                crawler.authenticate(target["credentials"])
            crawler.crawl(target["url"])
            crawlers.append(crawler)
            matches.extend(crawler.get_yara_matches())
    return matches, crawlers


def _unique_matches(matches: list[dict]) -> dict[tuple[str, str], dict]:
    """Uma entrada por (regra, página): várias ocorrências da string viram um só caso."""
    unique = {}
    for match in matches:
        unique.setdefault((match["rule_name"], match["link_match"]), match)
    return unique


def _case_title(e2e_id: str, match: dict) -> str:
    return f"[{e2e_id}] {match['client_match']} {match['rule_name']} {match['link_match']}"


def _create_cases(thehive_session, e2e_id, unique_matches, created_cases) -> dict:
    creator = CreateCase(thehive_session)
    cases = {}
    for key, match in sorted(unique_matches.items()):
        description = TemplateRenderer(
            CaseCommentTemplate.CASE_MONITORING_DNS_ALERT_YARA,
            dominio_suspeito=match["link_match"],
            regra_deteccao=match["rule_name"],
            cliente=match["client_match"],
        ).render()
        case_data = CaseDataType(
            title=_case_title(e2e_id, match),
            description=description,
            severity=3 if match["rule_type"] == "Leak" else 2,
            tags=[e2e_id, match["client_match"], match["rule_type"], "yara"],
            tlp=2,
            pap=2,
        )
        response, status = creator.create(case_data)
        assert 200 <= status < 300, response
        created_cases.append(response["_id"])
        cases[key] = response
    return cases


def _assert_crawl(crawlers, http_server, env, e2e_id):
    pages = env["pages"]
    visited = set().union(*(c.visited_urls for c in crawlers))
    errors = set().union(*(c.error_urls for c in crawlers))
    assert {pages["index"], pages["leak"], pages["vips"], pages["portal"]} <= visited
    assert errors == {pages["missing"], pages["down"]}
    requested = [(r["method"], r["path"]) for r in http_server.requests]
    assert ("GET", f"/{e2e_id}/missing.html") in requested
    assert requested.count(("GET", f"/{e2e_id}/leak.html")) == 1
    portal_requests = [r for r in http_server.requests if r["path"].endswith("/portal.html")]
    assert len(portal_requests) == 1
    scheme, _, token = portal_requests[0]["headers"]["Authorization"].partition(" ")
    assert scheme == "Basic"
    assert base64.b64decode(token).decode() == "analyst:s3cret"
    public_requests = [r for r in http_server.requests if r["path"].endswith("/index.html")]
    assert "Authorization" not in public_requests[0]["headers"]


def _assert_cases(thehive_session, e2e_id, env, cases, unique, expected, created_cases):
    alpha, beta = env["alpha"], env["beta"]
    getter = GetCase(thehive_session)
    for (rule_name, link), created in cases.items():
        client, rule_type = expected[(rule_name, link)]
        stored, status = getter.fetch_case(created["_id"])
        assert status == 200
        assert stored["title"] == _case_title(e2e_id, unique[(rule_name, link)])
        assert {e2e_id, client, rule_type, "yara"} <= set(stored["tags"])
        assert stored["severity"] == (3 if rule_type == "Leak" else 2)
        description = stored["description"]
        assert description.startswith("# Monitoramento DNS - REGRA YARA")
        assert f"- Nome do domínio: {link}" in description
        assert f"- Regra de Detecção: {rule_name}" in description
        assert f"- Client: {client}" in description

    listed, status = ListCase(thehive_session).list_cases(case_range="all")
    assert status == 200
    mine = [c for c in listed if e2e_id in (c.get("tags") or [])]
    assert sorted(c["_id"] for c in mine) == sorted(created_cases)
    by_tag = CaseLister(thehive_session).list_cases_by_tag(e2e_id)
    assert sorted(c["_id"] for c in by_tag) == sorted(created_cases)
    alpha_cases = [c for c in by_tag if alpha in c["tags"]]
    beta_cases = [c for c in by_tag if beta in c["tags"]]
    assert len(alpha_cases) == 2
    assert len(beta_cases) == 2
    assert not [c for c in by_tag if env["gamma"] in c["tags"]]


def _send_webhooks(thehive_session, http_server, e2e_id, env, cases, created_cases):
    alpha, beta = env["alpha"], env["beta"]
    getter = GetCase(thehive_session)
    webhook_url = http_server.add(
        f"/{e2e_id}/webhook", '{"ok": true}', content_type="application/json"
    )
    sent_ids = []
    sender = WebhookSender(
        webhook_url, timeout=5, max_retries=1, success_callback=lambda r: sent_ids.append(r.url)
    )
    for created in cases.values():
        stored, _ = getter.fetch_case(created["_id"])
        client = next(tag for tag in stored["tags"] if tag in (alpha, beta))
        response = sender.send(stored, headers={"X-Sadif-Client": client})
        assert response.status_code == 200
        assert response.json() == {"ok": True}
    webhook_requests = [r for r in http_server.requests if r["path"] == f"/{e2e_id}/webhook"]
    assert len(webhook_requests) == len(cases) == len(sent_ids)
    received = {json.loads(r["body"])["_id"]: r for r in webhook_requests}
    assert sorted(received) == sorted(created_cases)
    for case_id, request in received.items():
        body = json.loads(request["body"])
        assert request["method"] == "POST"
        assert request["headers"]["Content-Type"] == "application/json"
        assert request["headers"]["X-Sadif-Client"] in (alpha, beta)
        assert body["title"].startswith(f"[{e2e_id}] ")
        assert case_id in created_cases


def test_full_pipeline_client_rules_crawl_case_webhook(
    pipeline_env,
    mongo_client,
    thehive_session,
    e2e_id,
    http_server,
    local_git_repo,
    git_managers,
    created_cases,
):
    env = pipeline_env
    alpha, beta, pages, secrets = env["alpha"], env["beta"], env["pages"], env["secrets"]

    # 1) clientes a partir do repositório git client_monitoring
    clients = _import_clients(mongo_client, local_git_repo, git_managers, env)

    # 2) regras YARA dos clientes a partir do repositório git de regras
    _import_rules(mongo_client, local_git_repo, git_managers, env, clients)

    # 3) alvos do crawler a partir do repositório git crawler_monitoring
    targets = _import_targets(mongo_client, local_git_repo, git_managers, env)

    # 4) crawling de cada alvo
    matches, crawlers = _crawl(mongo_client, targets)
    _assert_crawl(crawlers, http_server, env, e2e_id)

    for match in matches:
        assert match["yara_match_condition"].identifier == "$s"
    unique = _unique_matches(matches)
    expected = {
        (f"{alpha}MonitoramentoLeak01", pages["leak"]): (alpha, "Leak"),
        (f"{alpha}MonitoramentoVips01", pages["vips"]): (alpha, "Vips"),
        (f"{beta}MonitoramentoLeak01", pages["leak"]): (beta, "Leak"),
        (f"{beta}MonitoramentoLeak01", pages["portal"]): (beta, "Leak"),
    }
    assert {key: (m["client_match"], m["rule_type"]) for key, m in unique.items()} == expected
    # duas ocorrências da string vip na mesma página -> um match (2 instâncias), um caso
    vips_matches = [m for m in matches if m["link_match"] == pages["vips"]]
    assert len(vips_matches) == 1
    assert len(vips_matches[0]["yara_match_condition"].instances) == 2
    assert all(secrets["orphan"] not in str(m) for m in matches)

    # 5) um caso no TheHive por match
    cases = _create_cases(thehive_session, e2e_id, unique, created_cases)
    assert len(cases) == len(expected)

    _assert_cases(thehive_session, e2e_id, env, cases, unique, expected, created_cases)

    # 6) rodar o pipeline de novo não duplica casos (mesmo título)
    creator = CreateCase(thehive_session)
    for match in unique.values():
        again = creator.create(CaseDataType(title=_case_title(e2e_id, match), tags=[e2e_id, "dup"]))
        assert again == "A case with the same title already exists"
    assert len(CaseLister(thehive_session).list_cases_by_tag(e2e_id)) == len(expected)

    # 7) cada caso é enviado por webhook
    _send_webhooks(thehive_session, http_server, e2e_id, env, cases, created_cases)


def test_pipeline_without_matches_creates_no_case(
    pipeline_env,
    mongo_client,
    thehive_session,
    e2e_id,
    http_server,
    local_git_repo,
    git_managers,
):
    """Clientes e regras importados, mas o alvo não contém nenhuma string monitorada."""
    env = pipeline_env
    clients = _import_clients(mongo_client, local_git_repo, git_managers, env)
    _import_rules(mongo_client, local_git_repo, git_managers, env, clients)
    clean = http_server.add(f"/{e2e_id}/clean.html", "<html><body>nada</body></html>")

    crawler = BaseCrawler(clean, depth=2, db_client=mongo_client)
    crawler.crawl(clean)
    assert crawler.visited_urls == {clean}
    assert crawler.get_yara_matches() == []
    assert CaseLister(thehive_session).list_cases_by_tag(e2e_id) == []


def test_pipeline_rules_of_unregistered_client_never_match(
    pipeline_env, mongo_client, e2e_id, http_server, local_git_repo, git_managers
):
    """Sem clientes cadastrados as regras não são importadas e o crawler não reporta matches."""
    env = pipeline_env
    assert ClientManager(mongo_client).list_all_clients() == []
    repo = local_git_repo(
        {"r/x.yar": _rule(f"{env['alpha']}MonitoramentoLeak01", env["secrets"]["alpha_leak"])}
    )
    importer = YaraRulesImporter(None, [], db_client=mongo_client, git_manager=git_managers(repo))
    summary = importer.import_rules()
    assert summary["imported"] == 0
    assert summary["ignored_rules"] == ["x.yar"]
    assert mongo_client[env["db"]["MONGODB_DATABASE_YARA"]].list_collection_names() == []

    page = env["pages"]["leak"]
    crawler = BaseCrawler(page, depth=0, db_client=mongo_client)
    crawler.crawl(page)
    assert crawler.visited_urls == {page}
    assert crawler.get_yara_matches() == []


def test_pipeline_reimport_with_overwrite_and_meta_update(
    pipeline_env, mongo_client, e2e_id, http_server, local_git_repo, git_managers
):
    """Reimportações (duplicadas, overwrite e meta_update) mantêm o pipeline consistente."""
    env = pipeline_env
    alpha = env["alpha"]
    clients = _import_clients(mongo_client, local_git_repo, git_managers, env)
    rules = _import_rules(mongo_client, local_git_repo, git_managers, env, clients)
    yara_db = mongo_client[env["db"]["MONGODB_DATABASE_YARA"]]

    # mesma regra com nova string: sem overwrite fica duplicada, com overwrite é atualizada
    name = f"{alpha}MonitoramentoLeak01"
    new_needle = f"alpha-new-{e2e_id}"
    repo = local_git_repo({f"{alpha}/{name}.yar": _rule(name, new_needle)})
    summary = YaraRulesImporter(
        None, clients, db_client=mongo_client, git_manager=git_managers(repo)
    ).import_rules()
    assert summary["duplicated_rules"] == [name]
    assert (
        env["secrets"]["alpha_leak"]
        in yara_db[f"Client_{alpha}"].find_one({"rule_name": name})["rule_content"]
    )

    summary = YaraRulesImporter(
        None, clients, db_client=mongo_client, git_manager=git_managers(repo), overwrite=True
    ).import_rules()
    assert summary["overwritten"] == 1
    page = http_server.add(f"/{e2e_id}/new.html", f"<html>{new_needle}</html>")
    crawler = BaseCrawler(page, depth=0, db_client=mongo_client)
    crawler.crawl(page)
    assert [(m["rule_name"], m["client_match"]) for m in crawler.get_yara_matches()] == [
        (name, alpha)
    ]
    old_page = env["pages"]["leak"]
    crawler = BaseCrawler(old_page, depth=0, db_client=mongo_client)
    crawler.crawl(old_page)
    assert name not in {m["rule_name"] for m in crawler.get_yara_matches()}

    # meta_update: as coleções dos clientes são recriadas só com as regras do repositório
    summary = YaraRulesImporter(
        None, clients, db_client=mongo_client, git_manager=git_managers(repo)
    ).import_rules(meta_update=True)
    assert summary["imported"] == 1
    assert yara_db[f"Client_{alpha}"].count_documents({}) == 1
    assert sorted(yara_db.list_collection_names()) == [f"Client_{alpha}"]
    assert len(rules) == 4

    # alvos do crawler: meta_update apaga os alvos antigos
    repo = local_git_repo(
        {"crawler_without_credential_web/only.json": json.dumps({"url": page, "depth": 0})}
    )
    importer = CrawlerManagerImporter(db_client=mongo_client, git_manager=git_managers(repo))
    _import_targets(mongo_client, local_git_repo, git_managers, env)
    result = importer.import_collections(meta_update=True)
    assert result["imported"] == [page]
    crawler_db = mongo_client[env["db"]["MONGODB_DATABASE_CRAWLER"]]
    assert [d["url"] for d in crawler_db["crawler_without_credential_web"].find()] == [page]
    assert crawler_db["crawler_with_credential_web"].count_documents({}) == 0


def test_pipeline_webhook_failure_is_reported(http_server, e2e_id):
    """Um webhook que responde erro levanta exceção depois de todas as tentativas."""
    import requests

    failing = http_server.add(f"/{e2e_id}/hook-fail", "boom", status=500)
    failures = []
    sender = WebhookSender(failing, timeout=2, max_retries=2, failure_callback=failures.append)
    with pytest.raises(requests.HTTPError):
        sender.send({"case": e2e_id})
    assert len(failures) == 2
    assert [r["path"] for r in http_server.requests] == [f"/{e2e_id}/hook-fail"] * 2
