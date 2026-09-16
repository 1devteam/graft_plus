import asyncio
import hashlib
import io
import json
import zipfile

import pytest

from graft_plus.fetch import CloneLimits, RepositoryLimitError, validate_checkout, validate_ref
from graft_plus.service import PACK_FILES, Artifact, ReconstructionApp, _parse_request, build_artifact


def test_request_accepts_only_public_repository_and_optional_ref():
    assert _parse_request(b'{"repository":"octocat/Hello-World","ref":"main"}') == (
        "octocat/Hello-World",
        "main",
    )
    with pytest.raises(ValueError):
        _parse_request(b'{"repository":"https://example.com/repo"}')
    with pytest.raises(ValueError):
        _parse_request(b'{"repository":"octocat/Hello-World","plan":true}')
    with pytest.raises(ValueError):
        _parse_request(b'{"repository":"octocat/Hello-World","ref":"../main"}')


@pytest.mark.parametrize("ref", ["--upload-pack=bad", "../main", "heads//main", "main.lock", "main/"])
def test_ref_rejects_unsafe_values(ref):
    with pytest.raises(ValueError):
        validate_ref(ref)


def test_checkout_rejects_symlinks_and_resource_overflow(tmp_path):
    target = tmp_path / "target"
    target.write_text("safe")
    (tmp_path / "link").symlink_to(target)
    with pytest.raises(RepositoryLimitError, match="symbolic"):
        validate_checkout(tmp_path, CloneLimits())

    (tmp_path / "link").unlink()
    with pytest.raises(RepositoryLimitError, match="materialized bytes"):
        validate_checkout(tmp_path, CloneLimits(max_total_bytes=1))


def test_build_artifact_uses_canonical_reconstruction(monkeypatch, tmp_path):
    subject = tmp_path / "fixture"
    (subject / "pkg").mkdir(parents=True)
    (subject / "pkg" / "__init__.py").write_text("")
    (subject / "pkg" / "core.py").write_text("VALUE = 1\n")

    materialized = []

    def fake_clone(_repository, dest, ref=None, limits=None):
        del ref, limits
        materialized.append(dest)
        dest.mkdir(parents=True)
        for path in subject.rglob("*"):
            relative = path.relative_to(subject)
            target = dest / relative
            if path.is_dir():
                target.mkdir(exist_ok=True)
            else:
                target.write_bytes(path.read_bytes())
        return dest

    monkeypatch.setattr("graft_plus.service.clone_public_repo", fake_clone)
    monkeypatch.setattr("graft_plus.cli._git_sha", lambda _subject: "a" * 40)

    artifact = build_artifact("owner/repo", "main")

    assert artifact.subject_sha == "a" * 40
    assert artifact.checksum == hashlib.sha256(artifact.body).hexdigest()
    assert materialized and not materialized[0].exists()
    with zipfile.ZipFile(io.BytesIO(artifact.body)) as archive:
        assert set(archive.namelist()) == set(PACK_FILES)
        assert archive.namelist()[0] == "AI-RECEIVER.md"
        assert b"Required answer discipline" in archive.read("AI-RECEIVER.md")
        graph = json.loads(archive.read("dependency-graph.v1.json"))
    assert graph["product"] == "G.R.A.F.T.+"
    assert artifact.node_count == graph["metrics"]["node_count"]


def _call_app(app, *, method, path, body=b"", origin=None):
    sent = []
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    headers = [] if origin is None else [(b"origin", origin.encode())]
    scope = {"type": "http", "method": method, "path": path, "headers": headers}
    asyncio.run(app(scope, receive, send))
    return sent


def test_health_is_no_store_and_origin_restricted():
    app = ReconstructionApp(concurrency=1)
    sent = _call_app(app, method="GET", path="/health")
    assert sent[0]["status"] == 200
    assert (b"cache-control", b"no-store") in sent[0]["headers"]

    blocked = _call_app(app, method="GET", path="/health", origin="https://evil.example")
    assert blocked[0]["status"] == 403


def test_reconstruct_returns_ephemeral_zip_headers(monkeypatch):
    artifact = Artifact(b"zip", "GRAFT-PACK-owner-repo-aaaaaaaa.zip", "a" * 40, "b" * 64, 3, 2)
    monkeypatch.setattr("graft_plus.service.build_artifact", lambda repository, ref: artifact)
    sent = _call_app(
        ReconstructionApp(concurrency=1),
        method="POST",
        path="/v1/reconstruct",
        body=b'{"repository":"owner/repo"}',
        origin="https://1devteam.com",
    )
    assert sent[0]["status"] == 200
    assert (b"content-type", b"application/zip") in sent[0]["headers"]
    assert (b"cache-control", b"no-store") in sent[0]["headers"]
    assert sent[1]["body"] == b"zip"
