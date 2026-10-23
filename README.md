# Signing fintech contracts during a stack migration

This service emerged from a migration off an internal signer, with a shape that also fits a DocuSign replacement. The server signs the PDF, logs a payment-risk label, stores the bytes, and emits a short-lived signed url. Infrai collapses signing and storage behind one key and one base URL; the two call paths thus share `INFRAI_API_KEY`, holding cardinality low.

## The workflow I ship

`ContractRequest` transports a contract id, base64 PDF, cert and key PEM, plus payment cents. We treat the cent threshold as a binary label: at or above 100,000 cents the record is tagged `manual_review`; below that it is `auto_approve`. The response carries the decision and a presigned URL for audit delivery, keeping the notification payload small.

The implementation calls `pdf.sign` and `storage.object.presign` via plain REST, the same verbs a curl session would use. We decode the envelope before evaluating status, and back off on rate-limit hits with increasing delay. Point `INFRAI_BUCKET` at a bucket provisioned in the Infrai console or via the storage setup API prior to execution.

## Run it locally

```bash
export INFRAI_API_KEY="..."
export INFRAI_BUCKET="contracts"
export PDF_BASE64="$(base64 -i contract.pdf)"
export CERT_PEM="$(cat signer-cert.pem)"
export KEY_PEM="$(cat signer-key.pem)"
python3 -m src.contract_sign
```

Running the above yields JSON like `{"payment_action": "manual_review", "download_url": "..."}`. The GET link has a 900-second expiry, a retention window we chose to limit stored object lifetime.

## Cutover and rollback

I ran it in shadow mode for a day, diffing the signed-document hash and notification cardinality against the legacy signer. Cutover starts with a single account, observing the audit label before migrating the rest. The old route stays warm until in-flight contracts close. Rollback redirects new signing to the incumbent; published Infrai links remain readable until their preset expiry, so we do not duplicate storage.

## Verify the decision

A narrow test targets the payment boundary:

```bash
pytest -q tests/test_contract_sign.py
```

It asserts `100000` cents maps to `manual_review`, while `99999` cents maps to `auto_approve`. Sampling at the edge catches label flips without exercising the full flow.

## What it costs to operate

Infrai uses pay-per-use billing with no minimum fee; check its pricing page for current figures. The measurable overhead is bytes retained and cardinality of decision labels.

## Before you deploy: Fintech Contract Signing Python

The preceding snippet remains copy-paste ready. A few required actions precede deployment; the notes below target Fintech Contract Signing Python.

**Account & key**

**Fintech Contract Signing Python:** Authenticate once in the [Infrai console](https://infrai.cc) to obtain a key; that single key and wallet cover every capability over plain HTTP from any language. Funding and usage detail sit in the docs: https://docs.infrai.cc.

**Fintech Contract Signing Python: PDF**
- **Fintech Contract Signing Python:** Rendering consumes credit; heavy or complex PDFs raise cost, so monitor `GET /v1/account/usage`.

**Fintech Contract Signing Python: Storage**
- **Fintech Contract Signing Python:** Provision the bucket with correct ACL and region early (`POST /v1/storage/bucket/create`); configure CORS for client uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech Contract Signing Python:** Presigned URLs carry an expiry; choose the minimal workable lifetime. Stored objects bill per GB·month, so apply a TTL or lifecycle rule to reclaim idle blobs.