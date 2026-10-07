import pytest

pytestmark = pytest.mark.e2e

import logging  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

from sadif.frameworks_drivers.gitmanager import GitManager  # noqa: E402

GIT_IDENTITY = ["-c", "user.name=e2e", "-c", "user.email=e2e@localhost"]


def _git(*args: str, cwd: str | Path | None = None) -> str:
    cmd = ["git", *GIT_IDENTITY]
    if cwd is not None:
        cmd += ["-C", str(cwd)]
    result = subprocess.run([*cmd, *args], check=True, capture_output=True, text=True)  # noqa: S603
    return result.stdout.strip()


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Identidade git determinística para os commits feitos pelo GitManager."""
    for var, value in {
        "GIT_AUTHOR_NAME": "sadif-e2e",
        "GIT_AUTHOR_EMAIL": "sadif-e2e@localhost",
        "GIT_COMMITTER_NAME": "sadif-e2e",
        "GIT_COMMITTER_EMAIL": "sadif-e2e@localhost",
    }.items():
        monkeypatch.setenv(var, value)


@pytest.fixture()
def managers():
    created: list[GitManager] = []

    def make(url: str, token: str | None = None) -> GitManager:
        manager = GitManager(url, token)
        created.append(manager)
        return manager

    yield make
    for manager in created:
        manager.cleanup()


@pytest.fixture()
def bare_repo(tmp_path: Path, e2e_id: str):
    """Repositório bare semeado (branch main) com um arquivo inicial."""

    def make(files: dict[str, str] | None = None) -> Path:
        files = files or {"seed.txt": f"seed {e2e_id}"}
        bare = tmp_path / f"{e2e_id}_{len(list(tmp_path.glob('*.git')))}.git"
        _git("init", "-q", "--bare", "-b", "main", str(bare))
        seed = tmp_path / f"seed_{bare.stem}"
        _git("clone", "-q", str(bare), str(seed))
        _git("checkout", "-q", "-b", "main", cwd=seed)
        for rel, content in files.items():
            path = seed / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        _git("add", "-A", cwd=seed)
        _git("commit", "-q", "-m", "seed", cwd=seed)
        _git("push", "-q", "origin", "main", cwd=seed)
        return bare

    return make


def _push_from_other_clone(bare: Path, tmp_path: Path, name: str, content: str, msg: str) -> str:
    other = tmp_path / f"other_{name}"
    _git("clone", "-q", "-b", "main", str(bare), str(other))
    (other / name).write_text(content, encoding="utf-8")
    _git("add", "-A", cwd=other)
    _git("commit", "-q", "-m", msg, cwd=other)
    _git("push", "-q", "origin", "main", cwd=other)
    return _git("rev-parse", "HEAD", cwd=other)


# --------------------------------------------------------------------------- init / auth


def test_init_creates_temp_dir_and_no_repo(managers, local_git_repo):
    url = local_git_repo({"a.txt": "a"})
    manager = managers(url)
    assert Path(manager.repo_dir).is_dir()
    assert list(Path(manager.repo_dir).iterdir()) == []
    assert manager.repo is None
    assert manager.repo_url == url
    assert manager.token is None


def test_token_is_injected_into_https_url(managers, e2e_id):
    token = f"tok{e2e_id}"
    manager = managers(f"https://git.example.invalid/{e2e_id}/repo.git", token)
    assert (
        manager.repo_url == f"https://x-access-token:{token}@git.example.invalid/{e2e_id}/repo.git"
    )


def test_token_is_ignored_for_non_https_url(managers, local_git_repo, e2e_id):
    url = local_git_repo({"a.txt": "a"})
    manager = managers(url, f"tok{e2e_id}")
    assert manager.repo_url == url
    cloned = manager.clone_repo()
    assert cloned == manager.repo_dir
    assert (Path(cloned) / "a.txt").read_text() == "a"


def test_clone_failure_with_token_does_not_leak_token(managers, http_server, e2e_id, caplog):
    # servidor local HTTP puro: o clone via https falha no handshake TLS, sem internet
    port = http_server.url.rsplit(":", 1)[1]
    token = f"tok{e2e_id}"
    manager = managers(f"https://127.0.0.1:{port}/{e2e_id}.git", token=token)
    assert token in manager.repo_url
    with caplog.at_level(logging.DEBUG):
        assert manager.clone_repo() is None
    assert manager.repo is None
    assert "Error cloning repository" in caplog.text
    assert token not in caplog.text


# --------------------------------------------------------------------------- clone


def test_clone_local_repo(managers, local_git_repo, e2e_id):
    url = local_git_repo({"dir/file.json": f'["{e2e_id}"]', "README.md": "hi"})
    manager = managers(url)
    cloned = manager.clone_repo()
    assert cloned == manager.repo_dir
    assert (Path(cloned) / "dir" / "file.json").read_text() == f'["{e2e_id}"]'
    assert (Path(cloned) / "README.md").read_text() == "hi"
    assert manager.repo is not None
    assert manager.repo.head.commit.hexsha == _git("rev-parse", "HEAD", cwd=url)
    assert manager.repo.active_branch.name == "main"


def test_clone_twice_returns_same_dir(managers, local_git_repo):
    manager = managers(local_git_repo({"a.txt": "a"}))
    first = manager.clone_repo()
    assert manager.clone_repo() == first
    assert (Path(first) / "a.txt").exists()


@pytest.mark.parametrize(
    "url",
    ["/nonexistent/path/{id}", "file:///nonexistent/{id}.git", "not a url {id}"],
)
def test_clone_invalid_url_returns_none(managers, e2e_id, url):
    manager = managers(url.format(id=e2e_id))
    assert manager.clone_repo() is None
    assert manager.repo is None


def test_clone_non_repo_directory_returns_none(managers, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "x.txt").write_text("x")
    assert managers(str(plain)).clone_repo() is None


# --------------------------------------------------------------------------- operations without clone


def test_operations_without_clone_fail_gracefully(managers, local_git_repo):
    manager = managers(local_git_repo({"a.txt": "a"}))
    assert manager.pull_changes() is False
    assert manager.commit_changes("msg") is False
    assert manager.push_changes() is False
    assert manager.repo is None


# --------------------------------------------------------------------------- pull


def test_pull_changes_fetches_new_commits(managers, bare_repo, tmp_path, e2e_id):
    bare = bare_repo()
    manager = managers(str(bare))
    cloned = Path(manager.clone_repo())
    assert not (cloned / "new.txt").exists()

    new_head = _push_from_other_clone(bare, tmp_path, "new.txt", e2e_id, "remote change")
    assert manager.pull_changes("main") is True
    assert (cloned / "new.txt").read_text() == e2e_id
    assert manager.repo.head.commit.hexsha == new_head


def test_pull_changes_up_to_date(managers, bare_repo):
    bare = bare_repo()
    manager = managers(str(bare))
    manager.clone_repo()
    before = manager.repo.head.commit.hexsha
    assert manager.pull_changes() is True
    assert manager.repo.head.commit.hexsha == before


def test_pull_changes_unknown_branch_fails(managers, bare_repo, e2e_id):
    manager = managers(str(bare_repo()))
    manager.clone_repo()
    before = manager.repo.head.commit.hexsha
    assert manager.pull_changes(f"missing-{e2e_id}") is False
    assert manager.repo.head.commit.hexsha == before


# --------------------------------------------------------------------------- commit


def test_commit_changes_adds_new_modified_and_deleted_files(managers, bare_repo, e2e_id):
    manager = managers(str(bare_repo({"keep.txt": "v1", "gone.txt": "bye"})))
    cloned = Path(manager.clone_repo())
    parent = manager.repo.head.commit.hexsha

    (cloned / "keep.txt").write_text("v2")
    (cloned / "gone.txt").unlink()
    (cloned / "sub").mkdir()
    (cloned / "sub" / "new.json").write_text(f'{{"id": "{e2e_id}"}}')

    message = f"update {e2e_id}"
    assert manager.commit_changes(message) is True

    head = manager.repo.head.commit
    assert head.message == message
    assert head.parents[0].hexsha == parent
    assert not manager.repo.is_dirty(untracked_files=True)
    files = set(_git("ls-tree", "-r", "--name-only", "HEAD", cwd=cloned).splitlines())
    assert files == {"keep.txt", "sub/new.json"}
    assert _git("show", "HEAD:keep.txt", cwd=cloned) == "v2"
    assert head.author.email == "sadif-e2e@localhost"


def test_commit_changes_nothing_to_commit(managers, bare_repo):
    manager = managers(str(bare_repo()))
    manager.clone_repo()
    before = manager.repo.head.commit.hexsha
    assert manager.commit_changes("noop") is False
    assert manager.repo.head.commit.hexsha == before


# --------------------------------------------------------------------------- push


def test_push_changes_lands_in_bare_repo(managers, bare_repo, e2e_id):
    bare = bare_repo()
    manager = managers(str(bare))
    cloned = Path(manager.clone_repo())
    (cloned / "pushed.txt").write_text(e2e_id)
    assert manager.commit_changes(f"push {e2e_id}") is True
    local_head = manager.repo.head.commit.hexsha

    assert manager.push_changes("main") is True
    assert _git("rev-parse", "main", cwd=bare) == local_head
    assert _git("show", "main:pushed.txt", cwd=bare) == e2e_id
    assert _git("log", "-1", "--format=%s", "main", cwd=bare) == f"push {e2e_id}"


def test_push_changes_multiple_commits(managers, bare_repo, e2e_id):
    bare = bare_repo()
    manager = managers(str(bare))
    cloned = Path(manager.clone_repo())
    for i in range(3):
        (cloned / f"f{i}.txt").write_text(f"{e2e_id}-{i}")
        assert manager.commit_changes(f"c{i}") is True
    assert manager.push_changes() is True
    log = _git("log", "--format=%s", "main", cwd=bare).splitlines()
    assert log[:4] == ["c2", "c1", "c0", "seed"]


def test_push_rejected_when_remote_diverged(managers, bare_repo, tmp_path, e2e_id):
    bare = bare_repo()
    manager = managers(str(bare))
    cloned = Path(manager.clone_repo())
    remote_head = _push_from_other_clone(bare, tmp_path, "remote.txt", "r", "remote")
    (cloned / "local.txt").write_text(e2e_id)
    assert manager.commit_changes("local") is True

    assert manager.push_changes("main") is False
    assert _git("rev-parse", "main", cwd=bare) == remote_head

    # depois do pull (merge) o push é aceito e ambos os arquivos chegam ao bare
    assert manager.pull_changes("main") is True
    assert manager.push_changes("main") is True
    assert _git("rev-parse", "main", cwd=bare) == manager.repo.head.commit.hexsha
    assert _git("show", "main:local.txt", cwd=bare) == e2e_id
    assert _git("show", "main:remote.txt", cwd=bare) == "r"


def test_push_unknown_local_branch_fails(managers, bare_repo, e2e_id):
    bare = bare_repo()
    manager = managers(str(bare))
    manager.clone_repo()
    before = _git("rev-parse", "main", cwd=bare)
    assert manager.push_changes(f"nobranch-{e2e_id}") is False
    assert _git("rev-parse", "main", cwd=bare) == before
    assert _git("branch", "--list", cwd=bare) == "* main"


def test_push_to_unreachable_remote_fails(managers, bare_repo, tmp_path):
    bare = bare_repo()
    manager = managers(str(bare))
    cloned = Path(manager.clone_repo())
    (cloned / "x.txt").write_text("x")
    manager.commit_changes("x")
    manager.repo.remote("origin").set_url(str(tmp_path / "vanished.git"))
    assert manager.push_changes() is False


def test_full_workflow_clone_pull_commit_push_cleanup(bare_repo, tmp_path, e2e_id):
    bare = bare_repo({"data/clients.json": "[]"})
    manager = GitManager(str(bare))
    cloned = Path(manager.clone_repo())
    _push_from_other_clone(bare, tmp_path, "upstream.txt", "u", "upstream")
    assert manager.pull_changes() is True
    (cloned / "data" / "clients.json").write_text(f'[{{"name": "{e2e_id}"}}]')
    assert manager.commit_changes("update clients") is True
    assert manager.push_changes() is True
    assert _git("show", "main:data/clients.json", cwd=bare) == f'[{{"name": "{e2e_id}"}}]'
    assert _git("show", "main:upstream.txt", cwd=bare) == "u"
    manager.cleanup()
    assert not cloned.exists()


# --------------------------------------------------------------------------- cleanup


def test_cleanup_removes_temp_dir(local_git_repo):
    manager = GitManager(local_git_repo({"a.txt": "a"}))
    repo_dir = Path(manager.clone_repo())
    assert (repo_dir / ".git").is_dir()
    manager.cleanup()
    assert not repo_dir.exists()
    assert manager.repo is None
    # idempotente
    manager.cleanup()
    assert not repo_dir.exists()


def test_cleanup_without_clone_removes_empty_dir(local_git_repo):
    manager = GitManager(local_git_repo({"a.txt": "a"}))
    repo_dir = Path(manager.repo_dir)
    assert repo_dir.is_dir()
    manager.cleanup()
    assert not repo_dir.exists()


def test_cleanup_after_failed_clone(e2e_id):
    manager = GitManager(f"/nonexistent/{e2e_id}")
    repo_dir = Path(manager.repo_dir)
    assert manager.clone_repo() is None
    manager.cleanup()
    assert not repo_dir.exists()


def test_clone_after_cleanup_recreates_dir(local_git_repo):
    manager = GitManager(local_git_repo({"a.txt": "a"}))
    first = manager.clone_repo()
    manager.cleanup()
    second = manager.clone_repo()
    try:
        assert second == first
        assert (Path(second) / "a.txt").read_text() == "a"
    finally:
        manager.cleanup()


# --------------------------------------------------------------------------- redaction on pull/push


def test_pull_and_push_failure_with_token_do_not_leak_token(
    managers, bare_repo, http_server, e2e_id, caplog
):
    # clone local, depois aponta origin para https local (falha TLS) com o token embutido.
    # Obs.: o git atual já remove credenciais do stderr; o teste protege contra regressões.
    bare = bare_repo()
    manager = managers(str(bare))
    cloned = Path(manager.clone_repo())
    token = f"tok{e2e_id}"
    manager.token = token
    port = http_server.url.rsplit(":", 1)[1]
    manager.repo.remote("origin").set_url(
        f"https://x-access-token:{token}@127.0.0.1:{port}/{e2e_id}.git"
    )
    (cloned / "y.txt").write_text(e2e_id)
    assert manager.commit_changes("y") is True
    before = _git("rev-parse", "main", cwd=bare)
    with caplog.at_level(logging.DEBUG):
        assert manager.pull_changes() is False
        assert manager.push_changes() is False
    assert "Error during pull" in caplog.text
    assert "Error during push" in caplog.text
    assert token not in caplog.text
    assert _git("rev-parse", "main", cwd=bare) == before


def test_token_injected_only_once(managers, e2e_id):
    token = f"tok{e2e_id}"
    manager = managers(f"https://host.invalid/redirect/https://x/{e2e_id}.git", token)
    assert manager.repo_url == (
        f"https://x-access-token:{token}@host.invalid/redirect/https://x/{e2e_id}.git"
    )
    assert manager.repo_url.count(token) == 1
