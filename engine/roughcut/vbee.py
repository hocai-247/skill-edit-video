"""Vbee speech-to-text client (async mode, one request at a time) with an on-disk cache.

Measured on the user's account (2026-10-06): utterance-level timestamps only, no
`stt-sync` feature (403), concurrent requests rejected (403 "Concurrent request limit"),
clips shorter than ~0.3 s come back FAILED, ~20-30 s per request.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import requests

API = "https://api.vbee.vn/v1/stt"
_LOCK = threading.Lock()   # the account allows one request in flight: serialize app-wide
_CACHE_LOCK = threading.Lock()


class VbeeAuthError(RuntimeError):
    pass


class VbeeError(RuntimeError):
    pass


def _unwrap(body: dict) -> dict:
    for key in ("result", "data"):
        if isinstance(body.get(key), dict) and "status" in body[key]:
            return body[key]
    return body


def _check(resp: requests.Response) -> dict:
    if resp.status_code in (401, 403):
        text = resp.text[:300]
        if "Concurrent request limit" in text:
            raise _Busy()
        if "credit" in text.lower():        # seen 2026-10-13: 403 "Failed to check credits with VBEE_TTS_API"
            raise VbeeAuthError("Vbee từ chối vì không kiểm tra được tín dụng tài khoản (403): tài khoản có thể "
                                "đã hết lượt, hoặc hệ thống tính tiền của Vbee đang lỗi. Xem số dư trên trang Vbee, "
                                "hoặc chọn nghe bằng máy này.")
        detail = "" if "<html" in text.lower() else f": {text}"   # nginx returns an HTML page
        raise VbeeAuthError(f"Vbee từ chối App ID/token ({resp.status_code}){detail}. "
                            "Kiểm tra lại App ID và token (hoặc quyền dùng speech-to-text của tài khoản).")
    if resp.status_code >= 300:
        body = resp.text[:300]
        if "<html" in body.lower():          # nginx error page: the HTML says nothing more than the code
            body = "máy chủ Vbee đang gặp sự cố, thử lại sau hoặc chọn nghe bằng máy này"
        raise VbeeError(f"Vbee lỗi {resp.status_code}: {body}")
    return _unwrap(resp.json())


class _Busy(Exception):
    pass


class VbeeClient:
    def __init__(self, app_id: str, token: str, poll: float = 3.0, timeout: float = 600.0):
        self.headers = {"Authorization": f"Bearer {token.strip()}", "App-Id": app_id.strip()}
        self.poll, self.timeout = poll, timeout

    def transcribe(self, wav: Path) -> str | None:
        """Text of a WAV clip; None if Vbee could not recognise anything (status FAILED)."""
        with _LOCK:
            for attempt in range(6):
                try:
                    return self._once(wav)
                except _Busy:
                    time.sleep(min(30, 5 * 2 ** attempt))
            raise VbeeError("Vbee báo đang xử lý yêu cầu khác quá lâu (Concurrent request limit)")

    def _once(self, wav: Path) -> str | None:
        with open(wav, "rb") as f:
            body = _check(requests.post(API, headers=self.headers,
                                        files={"audioContent": (wav.name, f, "audio/wav")},
                                        data={"mode": "async"}, timeout=120))
        tid = body.get("transcriptId")
        if not tid:
            raise VbeeError(f"Vbee không trả transcriptId: {json.dumps(body, ensure_ascii=False)[:300]}")
        deadline = time.time() + self.timeout
        while body.get("status") not in ("COMPLETED", "FAILED"):
            if time.time() > deadline:
                raise VbeeError(f"Vbee quá thời gian chờ cho {tid}")
            time.sleep(self.poll)
            body = _check(requests.get(f"{API}/transcripts/{tid}", headers=self.headers, timeout=60))
        if body["status"] == "FAILED":
            return None
        return (body.get("transcript") or "").strip() or None


class TextCache:
    """island text by (source sha256, start, end); survives across jobs so re-runs are free."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def file_key(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def load(self, key: str) -> dict:
        p = self._path(key)
        return json.loads(p.read_text()) if p.exists() else {}

    def put(self, key: str, start: float, end: float, text: str | None) -> None:
        self.put_key(key, f"{start:.3f}-{end:.3f}", text)

    def put_key(self, key: str, entry: str, value) -> None:
        with _CACHE_LOCK:
            data = self.load(key)
            data[entry] = value
            tmp = self._path(key).with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
            tmp.replace(self._path(key))

    @staticmethod
    def get(data: dict, start: float, end: float):
        k = f"{start:.3f}-{end:.3f}"
        return (True, data[k]) if k in data else (False, None)
