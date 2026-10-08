"""Stateless HTTP boundary for the canonical G.R.A.F.T.+ reconstruction engine."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from graft_plus.ascii_ir import ASCII_GRAPH_FILE
from graft_plus.change_set import CHANGE_SET_FILE
from graft_plus.cli import reconstruct
from graft_plus.fetch import CloneLimits, RepositoryLimitError, clone_public_repo, parse_public_repo, validate_ref
from graft_plus.residuals import LEDGER_FILE

AppReceive = Callable[[], Awaitable[dict[str, Any]]]
AppSend = Callable[[dict[str, Any]], Awaitable[None]]

MAX_REQUEST_BYTES = 8 * 1024
PACK_FILES = (
    "00-AI-READ-FIRST.md",
    ASCII_GRAPH_FILE,
    "dependency-graph.v1.json",
    CHANGE_SET_FILE,
    LEDGER_FILE,
    "graph-completeness-report.json",
    "graft-plus-receipt.json",
)
DEFAULT_ORIGINS = frozenset({"https://1devteam.com", "https://www.1devteam.com"})


class RequestError(ValueError):
    """A safe client-visible request error."""


class ReconstructionError(RuntimeError):
    """The canonical engine did not produce a valid downloadable pack."""


@dataclass(frozen=True, slots=True)
class Artifact:
    body: bytes
    filename: str
    subject_sha: str
    checksum: str
    node_count: int
    edge_count: int


def _allowed_origins() -> frozenset[str]:
    configured = os.getenv("GRAFT_ALLOWED_ORIGINS")
    if not configured:
        return DEFAULT_ORIGINS
    return frozenset(item.strip() for item in configured.split(",") if item.strip())


def _cors_headers(origin: str | None) -> list[tuple[bytes, bytes]]:
    if origin not in _allowed_origins():
        return []
    return [
        (b"access-control-allow-origin", origin.encode("ascii")),
        (b"access-control-allow-methods", b"POST, OPTIONS"),
        (b"access-control-allow-headers", b"content-type"),
        (
            b"access-control-expose-headers",
            b"content-disposition, x-graft-checksum, x-graft-subject-sha, x-graft-node-count, x-graft-edge-count",
        ),
        (b"vary", b"Origin"),
    ]


async def _request_body(receive: AppReceive) -> bytes:
    body = bytearray()
    while True:
        message = await receive()
        if message.get("type") != "http.request":
            continue
        body.extend(message.get("body", b""))
        if len(body) > MAX_REQUEST_BYTES:
            raise RequestError("request body is too large")
        if not message.get("more_body", False):
            return bytes(body)


def _parse_request(body: bytes) -> tuple[str, str | None]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RequestError("request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise RequestError("request body must be a JSON object")
    unknown = set(payload) - {"repository", "ref"}
    if unknown:
        raise RequestError(f"unknown request fields: {', '.join(sorted(unknown))}")
    repository = payload.get("repository")
    ref = payload.get("ref")
    if not isinstance(repository, str) or not repository.strip():
        raise RequestError("repository must be a public GitHub owner/repo or URL")
    if ref is not None and not isinstance(ref, str):
        raise RequestError("ref must be a string")
    try:
        parse_public_repo(repository)
        safe_ref = validate_ref(ref) if ref is not None else None
    except ValueError as exc:
        raise RequestError(str(exc)) from exc
    return repository, safe_ref


def _zip_pack(out: Path) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in PACK_FILES:
            path = out / name
            if not path.is_file():
                raise ReconstructionError(f"canonical engine did not emit {name}")
            archive.writestr(name, path.read_bytes())
    return stream.getvalue()


def build_artifact(repository: str, ref: str | None, limits: CloneLimits | None = None) -> Artifact:
    """Run one bounded reconstruction and return bytes after temporary data is gone."""
    owner, repo = parse_public_repo(repository)
    with tempfile.TemporaryDirectory(prefix="graft-api-") as raw:
        workspace = Path(raw)
        subject = clone_public_repo(repository, workspace / "subject", ref=ref, limits=limits)
        out = workspace / "pack"
        if reconstruct(subject, out, None, None, None) != 0:
            raise ReconstructionError("canonical reconstruction failed integrity checks")
        receipt = json.loads((out / "graft-plus-receipt.json").read_text(encoding="utf-8"))
        graph = json.loads((out / "dependency-graph.v1.json").read_text(encoding="utf-8"))
        subject_sha = receipt.get("subject_sha")
        if not isinstance(subject_sha, str) or len(subject_sha) != 40:
            raise ReconstructionError("canonical receipt is missing the resolved commit SHA")
        body = _zip_pack(out)
    checksum = hashlib.sha256(body).hexdigest()
    filename = f"GRAFT-PACK-{owner}-{repo}-{subject_sha[:8]}.zip"
    metrics = graph.get("metrics") or {}
    return Artifact(
        body=body,
        filename=filename,
        subject_sha=subject_sha,
        checksum=checksum,
        node_count=int(metrics.get("node_count", 0)),
        edge_count=int(metrics.get("edge_count", 0)),
    )


async def _respond(
    send: AppSend,
    status: int,
    body: bytes,
    headers: list[tuple[bytes, bytes]],
    content_type: bytes,
) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", content_type), (b"cache-control", b"no-store"), *headers],
        }
    )
    await send({"type": "http.response.body", "body": body})


class ReconstructionApp:
    """Dependency-free ASGI application exposing only health and reconstruction."""

    def __init__(self, *, concurrency: int | None = None) -> None:
        configured = concurrency or int(os.getenv("GRAFT_MAX_CONCURRENCY", "2"))
        self._semaphore = asyncio.Semaphore(max(1, configured))

    async def __call__(self, scope: dict[str, Any], receive: AppReceive, send: AppSend) -> None:
        if scope.get("type") != "http":
            return
        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", "/"))
        headers = {bytes(k).lower(): bytes(v) for k, v in scope.get("headers", [])}
        origin_raw = headers.get(b"origin")
        origin = origin_raw.decode("ascii", errors="ignore") if origin_raw else None
        cors = _cors_headers(origin)
        if origin and not cors:
            await _respond(send, 403, b'{"error":"origin is not allowed"}', [], b"application/json")
            return
        if method == "OPTIONS" and path == "/v1/reconstruct":
            await _respond(send, 204, b"", cors, b"text/plain")
            return
        if method == "GET" and path == "/health":
            await _respond(
                send,
                200,
                b'{"product":"G.R.A.F.T.+","role":"fact-substrate","status":"ok"}',
                cors,
                b"application/json",
            )
            return
        if method != "POST" or path != "/v1/reconstruct":
            await _respond(send, 404, b'{"error":"not found"}', cors, b"application/json")
            return
        try:
            repository, ref = _parse_request(await _request_body(receive))
            async with self._semaphore:
                artifact = await asyncio.to_thread(build_artifact, repository, ref)
        except RequestError as exc:
            await _respond(send, 400, json.dumps({"error": str(exc)}).encode(), cors, b"application/json")
            return
        except RepositoryLimitError as exc:
            await _respond(send, 413, json.dumps({"error": str(exc)}).encode(), cors, b"application/json")
            return
        except TimeoutError as exc:
            await _respond(send, 504, json.dumps({"error": str(exc)}).encode(), cors, b"application/json")
            return
        except ReconstructionError as exc:
            await _respond(send, 422, json.dumps({"error": str(exc)}).encode(), cors, b"application/json")
            return
        except RuntimeError:
            await _respond(send, 502, b'{"error":"unable to materialize public repository"}', cors, b"application/json")
            return
        response_headers = [
            (b"content-disposition", f'attachment; filename="{artifact.filename}"'.encode("ascii")),
            (b"x-graft-checksum", f"sha256:{artifact.checksum}".encode("ascii")),
            (b"x-graft-subject-sha", artifact.subject_sha.encode("ascii")),
            (b"x-graft-node-count", str(artifact.node_count).encode("ascii")),
            (b"x-graft-edge-count", str(artifact.edge_count).encode("ascii")),
            *cors,
        ]
        await _respond(send, 200, artifact.body, response_headers, b"application/zip")


app = ReconstructionApp()


def main() -> None:
    """Run the service with the optional production ASGI dependency."""
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit('install the service extra: pip install "graft_plus[service]"') from exc
    uvicorn.run(
        "graft_plus.service:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
    )
