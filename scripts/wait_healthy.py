"""Block until every docker-compose service answers, or fail with a per-service diagnosis.

stdlib-only on purpose: this runs right after `docker compose up -d`, possibly before
`uv sync` — it must not depend on the project's own dependencies being installed.
Qdrant gets its readiness check here because its distroless image cannot run an
in-container healthcheck (see docker-compose.yml header note).
"""

from __future__ import annotations

import socket
import sys
import time
import urllib.error
import urllib.request

TIMEOUT_S = 180
POLL_S = 3

HTTP_CHECKS = {
    "neo4j (http)": "http://localhost:7474",
    "qdrant": "http://localhost:6333/readyz",
    "langfuse": "http://localhost:3000/api/public/health",
    "temporal-ui": "http://localhost:8233",
}
TCP_CHECKS = {
    "temporal (grpc)": ("localhost", 7233),
}


def http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=4) as resp:  # noqa: S310 (localhost only)
            return 200 <= resp.status < 400
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False


def tcp_ok(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=4):
            return True
    except OSError:
        return False


def main() -> int:
    pending = dict(HTTP_CHECKS) | {name: addr for name, addr in TCP_CHECKS.items()}
    deadline = time.time() + TIMEOUT_S
    while pending and time.time() < deadline:
        for name in list(pending):
            target = pending[name]
            ok = http_ok(target) if isinstance(target, str) else tcp_ok(*target)
            if ok:
                print(f"  [ok] {name}")
                del pending[name]
        if pending:
            waiting = ", ".join(sorted(pending))
            print(f"  ...waiting on: {waiting}")
            time.sleep(POLL_S)
    if pending:
        print(f"\nFAILED after {TIMEOUT_S}s. Still unhealthy: {', '.join(sorted(pending))}")
        print("Diagnose with: docker compose ps ; docker compose logs <service> --tail 50")
        return 1
    print("\nAll services healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
