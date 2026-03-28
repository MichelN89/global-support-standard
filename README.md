# Global Support Standard (GSS) Python MVP

This repository contains an end-to-end MVP for the GSS briefing:

- `gss_provider` (FastAPI): mock shop provider implementing core GSS endpoints
- `gss` (Typer CLI): consumer command interface using `gss <shop> <domain> <action>`
- YAML protocol engine for shop-defined resolution logic
- Basic auth/session flow, confirmation-token actions, and audit logging

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run Provider

```bash
gss-provider
```

Provider runs on `http://127.0.0.1:8000/v1`.

## Use CLI

```bash
gss mockshop.local describe
gss mockshop.local auth login --method api_key --customer-id CUST-001
gss mockshop.local orders list
gss mockshop.local orders get --id ORD-1001
gss mockshop.local shipping track --order-id ORD-1001
gss mockshop.local protocols get --trigger delivery-not-received --context '{"order_id":"ORD-1002","days_since_expected":1}'
gss mockshop.local returns initiate --order-id ORD-1001 --item-id ITEM-1 --reason defective
gss mockshop.local returns confirm --token <confirmation_token>
gss mockshop.local account audit-log
```

## Implemented MVP Features

- Discovery:
  - `GET /v1/describe`
  - `GET /v1/{domain}/describe`
- Auth:
  - `POST /v1/auth/login`
- Domains:
  - `orders list/get`
  - `shipping track`
  - `returns check-eligibility/initiate/confirm`
  - `protocols get`
  - `account audit-log`
- Security baseline:
  - Authorization token required for protected endpoints
  - required `GSS-Consumer-*` headers
  - two-step confirmation token flow for request actions
  - append-only audit log records

## Test

```bash
pytest
```
