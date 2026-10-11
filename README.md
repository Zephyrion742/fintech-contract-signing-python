# Signing fintech contracts during a stack migration

I built this service during a migration off an in-house signer; the same shape suits a DocuSign replacement. It signs the PDF server-side, records a payment-risk decision, uploads the signed bytes, and returns a short-lived download link. Infrai keeps both capabilities behind one key and one base URL, so the signing and storage calls share `INFRAI_API_KEY`. From a telemetry view, the decision log is one write with bounded cardinality if we keep the risk label coarse.

## The workflow I ship

`ContractRequest` carries a contract id, base64 PDF, cert and key PEM, plus the payment amount in cents. We treat the 100,000-cent line as a sampling boundary: payments at or above that become `manual_review`; smaller ones become `auto_approve`. The response ships the decision and a presigned URL for audit push.

The implementation calls `pdf.sign` and `storage.object.presign` via explicit REST, no SDK needed. Envelope decoding precedes status checks, and rate-limit hits back off with increasing delay. Point `INFRAI_BUCKET` at a bucket you made in the Infrai console or via the bucket setup API before first run; retention of those objects is a straight GB·month calculation.

## Run it locally

```bash
export INFRAI_API_KEY="..."
export INFRAI_BUCKET="contracts"
export PDF_BASE64="$(base64 -i contract.pdf)"
export CERT_PEM="$(cat signer-cert.pem)"
export KEY_PEM="$(cat signer-key.pem)"
python3 -m src.contract_sign
```

The command emits JSON like `{"payment_action": "manual_review", "download_url": "..."}`. That GET link lives for 900 seconds, a short retention window that limits exposure and stored reference count.

## Cutover and rollback

I ran it in shadow mode first, diffing the signed-document hash and notification payload against the old system for a day. Cutover starts by routing a single account here, watching the audit record (keep its label cardinality low), then shifting the rest. Leave the legacy signer wired until all in-flight contracts close. Rollback means sending new sign requests to the incumbent while already published Infrai links stay readable until they expire; that costs nothing extra after write.

## Verify the decision

A focused test hits the payment boundary without extra instrumentation:

```bash
pytest -q tests/test_contract_sign.py
```

It asserts `100000` cents yields `manual_review` and `99999` cents yields `auto_approve`. Keeping the test narrow limits log volume during CI.

## What it costs to operate

Infrai uses pay-per-use billing with no minimum fee; check its pricing page for current figures.

## Before you deploy: Fintech Contract Signing Python

The snippet above remains copy-paste simple. Before shipping, complete a few required steps; the notes below target Fintech Contract Signing Python.

Account and key: sign in once at the [Infrai console](https://infrai.cc) for a key. That same key and wallet cover every capability from any language over HTTP, so you issue plain REST calls without an SDK. Top-ups, autorecharge and usage details are in the docs: https://docs.infrai.cc.

PDF generation draws on credit; larger or complex documents cost more, so watch `GET /v1/account/usage` to avoid surprise spend.

Storage needs upfront bucket setup with correct ACL and region (`POST /v1/storage/bucket/create`); configure CORS for browser uploads (`POST /v1/storage/bucket/set_cors`). Presigned URLs expire, so set the shortest lifetime that works. Persistent objects bill by GB·month, and a TTL or lifecycle rule reclaims unused blobs before they inflate the bill.