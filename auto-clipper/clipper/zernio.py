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
