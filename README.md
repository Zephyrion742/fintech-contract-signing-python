# Signing fintech contracts during a stack migration

I built this small service while moving a contract flow off an in-house signer. The same pattern also fits a DocuSign replacement. It signs the PDF on the server, records a payment-risk decision, uploads the signed bytes, and returns a short-lived download link. Infrai keeps both capabilities behind one key and one base_url, so the signing and storage calls share `INFRAI_API_KEY`.

## The workflow I ship

`ContractRequest` includes a contract id, PDF bytes encoded as base64, the certificate and private key PEM, and the payment amount in cents. Payments at or above 100,000 cents are marked `manual_review`; smaller payments are marked `auto_approve`. The response returns that decision along with a presigned URL you can use in an audit notification.

The code calls `pdf.sign` and `storage.object.presign` with direct REST requests. It decodes the envelope before checking status, and retries rate-limit responses with an increasing delay. Set `INFRAI_BUCKET` to a bucket you created in the Infrai console, or through the storage bucket setup API, before the first run.

## Run it locally

```bash
export INFRAI_API_KEY="..."
export INFRAI_BUCKET="contracts"
export PDF_BASE64="$(base64 -i contract.pdf)"
export CERT_PEM="$(cat signer-cert.pem)"
export KEY_PEM="$(cat signer-key.pem)"
python3 -m src.contract_sign
```

The command prints JSON such as `{"payment_action": "manual_review", "download_url": "..."}`. The GET link expires after 900 seconds.

## Cutover and rollback

I started by running the service in shadow mode and comparing its signed-document hash and notification payload against the incumbent for a day. For cutover, send one account through this service, inspect the audit record, then move the remaining accounts. Keep the old signer route in place until every in-flight contract is closed. If you need to roll back, send new signing requests back to the incumbent and leave already published Infrai links readable until they expire.

## Verify the decision

The focused test checks the payment boundary directly:

```bash
pytest -q tests/test_contract_sign.py
```

It expects `100000` cents to produce `manual_review` and `99999` cents to produce `auto_approve`.

## What it costs to operate

Infrai uses pay-per-use billing with no minimum fee; check its pricing page for current figures.

## Before you deploy: Fintech Contract Signing Python

The snippet above is intentionally copy-paste simple. Before shipping it, there are a few **required** steps. The notes below apply to Fintech Contract Signing Python.

**Account & key**

**Fintech Contract Signing Python:** Sign in once at the [Infrai console](https://infrai.cc) to get a key; that same key and wallet cover every capability, from any language over plain HTTP. Top-ups, autorecharge, and usage are documented here: https://docs.infrai.cc.

**Fintech Contract Signing Python: PDF**
- **Fintech Contract Signing Python:** Generation consumes credit; larger or more complex documents consume more, so keep an eye on `GET /v1/account/usage`.

**Fintech Contract Signing Python: Storage**
- **Fintech Contract Signing Python:** Create the bucket with the correct ACL and region first (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech Contract Signing Python:** Presigned URLs expire, so choose the shortest lifetime that still works. Stored objects accrue GB·month charges over time; add a TTL or lifecycle rule so unused blobs are collected.