"""Minimal Zernio REST client: upload a video and create a scheduled post."""
import os
import time
import uuid
from pathlib import Path

import requests

from .util import log

API = os.environ.get("ZERNIO_API_URL", "https://zernio.com/api/v1")


class Zernio:
    def __init__(self) -> None:
        key = os.environ.get("ZERNIO_API_KEY")
        if not key:
            raise RuntimeError("ZERNIO_API_KEY is required to post")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {key}", "Content-Type": "application/json"})

    def _req(self, method: str, path: str, **kw) -> requests.Response:
        for attempt in range(4):
            r = self.s.request(method, f"{API}{path}", timeout=120, **kw)
            if r.status_code < 500 and r.status_code != 429:
                return r
            time.sleep(2 ** attempt * 3)
        return r

    def list_accounts(self) -> list[dict]:
        r = self._req("GET", "/accounts")
        r.raise_for_status()
        return r.json().get("accounts", [])

    def resolve_accounts(self, wanted: list[dict], blocked: set[str]) -> list[dict]:
        """Turn config entries into [{platform, account_id}] using only accounts this API key owns.

        An entry may give `account_id`, or `username` (matched case-insensitively), or neither
        (then every connected account on that platform is used). Blocked ids are never returned.
        """
        owned = self.list_accounts()
        owned_ids = {a["_id"] for a in owned}
        out = []
        for w in wanted:
            platform = w["platform"]
            if w.get("account_id"):
                matches = [a for a in owned if a["_id"] == str(w["account_id"])]
                if not matches:
                    raise RuntimeError(f"Account {w['account_id']} is not connected to this ZERNIO_API_KEY")
            else:
                matches = [a for a in owned if a.get("platform") == platform]
                if w.get("username"):
                    u = w["username"].lstrip("@").lower()
                    matches = [a for a in matches if str(a.get("username", "")).lstrip("@").lower() == u]
            for a in matches:
                if a["_id"] in blocked:
                    raise RuntimeError(f"Refusing to post: account {a['_id']} ({a.get('username')}) is in blocked_account_ids")
                out.append({"platform": a["platform"], "account_id": a["_id"], "username": a.get("username")})
        if not out:
            raise RuntimeError(f"No matching accounts for this ZERNIO_API_KEY (connected: "
                               f"{[(a.get('platform'), a.get('username')) for a in owned]})")
        assert all(o["account_id"] in owned_ids for o in out)
        return out

    def upload(self, path: Path) -> str:
        r = self._req("POST", "/media/presign", json={"filename": path.name, "contentType": "video/mp4",
                                                      "size": path.stat().st_size})
        r.raise_for_status()
        data = r.json()
        with path.open("rb") as fh:
            put = requests.put(data["uploadUrl"], data=fh, headers={"Content-Type": "video/mp4"}, timeout=900)
        put.raise_for_status()
        log(f"[zernio] uploaded {path.name}")
        return data["publicUrl"]

    def create_post(self, body: dict, idempotency_key: str | None = None) -> dict:
        key = idempotency_key or str(uuid.uuid4())
        r = self._req("POST", "/posts", json=body, headers={"Idempotency-Key": key})
        if r.status_code == 409:  # same content already posted to this account recently
            log("[zernio] duplicate post (409) - treating as done")
            return {"duplicate": True}
        if not r.ok:
            raise RuntimeError(f"Zernio create post failed {r.status_code}: {r.text[:500]}")
        return r.json()
