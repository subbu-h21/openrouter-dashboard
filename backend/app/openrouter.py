"""Minimal read-only client for the OpenRouter management API (stdlib only)."""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

BASE_URL = "https://openrouter.ai/api/v1"
MAX_QUERY_ROWS = 10000


class OpenRouterError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"OpenRouter API error {status}: {message}")
        self.status = status


class OpenRouterClient:
    def __init__(self, management_key: str):
        self._key = management_key

    def _request(self, method: str, path: str, body: dict | None = None, retries: int = 4):
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(retries + 1):
            req = urllib.request.Request(
                BASE_URL + path,
                method=method,
                data=data,
                headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")[:500]
                try:
                    message = json.loads(text)["error"]["message"]
                except Exception:
                    message = text
                if (e.code == 429 or e.code >= 500) and attempt < retries:
                    wait = float(e.headers.get("Retry-After") or 0) or 2 ** (attempt + 1)
                    log.warning("OpenRouter %s on %s, retrying in %.0fs", e.code, path, wait)
                    time.sleep(min(wait, 60))
                    continue
                raise OpenRouterError(e.code, message) from None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < retries:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise OpenRouterError(0, f"network error: {e}") from None

    def analytics_query(self, body: dict) -> tuple[list[dict], bool]:
        """Returns (rows, truncated)."""
        result = self._request("POST", "/analytics/query", body)["data"]
        return result["data"], bool(result.get("metadata", {}).get("truncated"))

    def credits(self) -> dict:
        return self._request("GET", "/credits")["data"]

    def list_keys(self) -> list[dict]:
        keys, seen, offset = [], set(), 0
        for _ in range(100):
            qs = urllib.parse.urlencode({"include_disabled": "true", "include_expired": "true", "offset": offset})
            page = self._request("GET", f"/keys?{qs}")["data"]
            new = [k for k in page if k["hash"] not in seen]
            if not new:  # empty page, or the API ignored the offset
                break
            keys.extend(new)
            seen.update(k["hash"] for k in new)
            offset += len(page)
        return keys
