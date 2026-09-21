from __future__ import annotations

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

EXPECTED_VERSION = "1.0.0"


def fetch(url: str) -> tuple[int, bytes, str]:
    request = Request(url, headers={"User-Agent": "SecureDesk-SmokeTest/1.0"})
    with urlopen(request, timeout=20) as response:  # noqa: S310 - explicit operator-provided URL
        return response.status, response.read(), response.headers.get("Content-Type", "")


def run(base_url: str) -> None:
    base_url = base_url.rstrip("/")

    status, body, _ = fetch(f"{base_url}/")
    if status != 200 or b"SecureDesk" not in body:
        raise RuntimeError("Frontend check failed")
    print("[ok] frontend")

    status, body, _ = fetch(f"{base_url}/api/health")
    health = json.loads(body)
    if status != 200 or health != {"status": "ok"}:
        raise RuntimeError("Health check failed")
    print("[ok] health")

    status, body, _ = fetch(f"{base_url}/api/openapi.json")
    schema = json.loads(body)
    if status != 200 or schema.get("info", {}).get("version") != EXPECTED_VERSION:
        raise RuntimeError("OpenAPI version check failed")
    print(f"[ok] OpenAPI {EXPECTED_VERSION}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/smoke_test.py https://your-securedesk.example")

    try:
        run(sys.argv[1])
    except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"Smoke test failed: {exc}") from None

    print("SecureDesk production smoke test passed.")


if __name__ == "__main__":
    main()
