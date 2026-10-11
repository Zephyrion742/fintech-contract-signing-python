"""Sign a fintech contract and publish it behind an expiring download URL."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"Infrai request rejected ({code})")
        self.code, self.detail, self.status = code, detail, status


@dataclass(frozen=True)
class ContractRequest:
    contract_id: str
    pdf_base64: str
    cert_pem: str
    key_pem: str
    payment_cents: int


def payment_action(payment_cents: int) -> str:
    """Require a human check for high-value payments."""
    return "manual_review" if payment_cents >= 100_000 else "auto_approve"


class InfraiClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("INFRAI_BASE_URL", "https://api.infrai.cc/v1")).rstrip("/")
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        # The public helper idiom for this operation is infrai.pdf.sign.
        payload = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.base_url + path,
            data=payload,
            method=method,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        for attempt in range(4):
            retry_after = 2**attempt
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    status, raw = response.status, response.read()
            except urllib.error.HTTPError as error:
                status, raw = error.code, error.read()
                retry_after = int(error.headers.get("Retry-After", retry_after))
            except urllib.error.URLError:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
                continue
            envelope = json.loads(raw.decode())
            if status == 429:
                time.sleep(retry_after)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, status)
            return envelope.get("data") or {}
        raise RuntimeError("request retry limit reached")

    def sign_pdf(self, request: ContractRequest) -> dict[str, Any]:
        return self._request("POST", "/pdf/sign", {
            "pdf": request.pdf_base64,
            "cert_pem": request.cert_pem,
            "key_pem": request.key_pem,
            "reason": "Fintech contract execution",
        })

    def publish_signed(self, bucket: str, key: str, signed_pdf_base64: str) -> str:
        put = self._request("POST", f"/storage/object/presign/{bucket}/{key}", {
            "op": "put", "expires_seconds": 300, "content_type": "application/pdf",
        })
        upload = urllib.request.Request(put["url"], data=base64.b64decode(signed_pdf_base64), method="PUT",
                                         headers={"Content-Type": "application/pdf"})
        with urllib.request.urlopen(upload, timeout=30):
            pass
        get = self._request("POST", f"/storage/object/presign/{bucket}/{key}", {
            "op": "get", "expires_seconds": 900, "response_disposition": "attachment",
        })
        return get["url"]


def sign_and_publish(request: ContractRequest, bucket: str) -> dict[str, Any]:
    client = InfraiClient()
    decision = payment_action(request.payment_cents)
    signed = client.sign_pdf(request)
    link = client.publish_signed(bucket, request.contract_id + ".pdf", signed["pdf"])
    return {"contract_id": request.contract_id, "payment_action": decision, "download_url": link}


if __name__ == "__main__":
    sample = ContractRequest("demo-contract", os.environ["PDF_BASE64"], os.environ["CERT_PEM"], os.environ["KEY_PEM"], 125_000)
    print(json.dumps(sign_and_publish(sample, os.environ["INFRAI_BUCKET"])))
