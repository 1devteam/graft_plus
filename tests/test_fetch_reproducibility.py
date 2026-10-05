from types import SimpleNamespace

from graft_plus.fetch import CloneLimits, clone_public_repo


def test_exact_commit_ref_uses_fetch_and_detached_checkout(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((list(cmd), kwargs.get("cwd")))
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("graft_plus.fetch.subprocess.run", fake_run)
    destination = tmp_path / "subject"
    sha = "d5fd7217fb66e57b64eed42d0e091bd1aba9d33b"

    result = clone_public_repo(
        "chromium/chromium",
        dest=destination,
        ref=sha,
        limits=CloneLimits(timeout_seconds=5),
    )

    assert result == destination
    commands = [cmd for cmd, _cwd in calls]
    assert ["git", "init"] in commands
    assert ["git", "remote", "add", "origin", "https://github.com/chromium/chromium.git"] in commands
    assert ["git", "fetch", "--depth", "1", "origin", sha] in commands
    assert ["git", "checkout", "--detach", "FETCH_HEAD"] in commands
    assert not any("--branch" in cmd for cmd in commands)


def test_unpinned_subject_keeps_bounded_shallow_clone(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("graft_plus.fetch.subprocess.run", fake_run)
    destination = tmp_path / "subject"
    clone_public_repo("owner/repo", dest=destination, limits=CloneLimits(timeout_seconds=5))

    assert calls == [["git", "clone", "--depth", "1", "https://github.com/owner/repo.git", str(destination)]]
