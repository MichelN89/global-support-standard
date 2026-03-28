# Shopify Integration Example

This project shows the exact boundary you asked for: GSS standard logic is reusable, while all webshop behavior remains owned by the webshop implementation.

## Ownership Split (Important)

- GSS packages (`src/gss_core`, `src/gss_provider`) own:
  - protocol contracts
  - request/response envelope semantics
  - validation and shared action-level behavior
- Teststore webshop project (`src/gss_webshop_shopify`) owns:
  - Shopify credentials and API access
  - token/session behavior (runtime adapter)
  - audit persistence choice
  - business rollout choices (supported/unsupported commands)

So no production customer data needs to flow through "central GSS servers"; this provider runs in the webshop deployment.

## Current Endpoints

- Implemented:
  - `describe`
  - `auth verify-customer` (identity proof with order+email/phone, or phone recovery)
  - `auth issue-token` (one-time verification exchange for short-lived token)
  - `auth login` (legacy dev shortcut)
  - `orders list`
  - `orders get`
  - `shipping track`
- Explicitly unsupported:
  - `account get`
  - `payments get`

Unsupported actions intentionally return `ACTION_NOT_SUPPORTED`.

## Local Setup

1) Create local env:

```bash
cp webshop/shopify-test-store/.env.example webshop/shopify-test-store/.env
```

2) Edit env values in `webshop/shopify-test-store/.env`:
- `GSS_SHOP_NAME=Example Shop`
- `SHOPIFY_SHOP_DOMAIN=your-store.myshopify.com`
- `SHOPIFY_ADMIN_TOKEN=...`

3) Start provider with env loaded:

```bash
webshop/shopify-test-store/run-local.sh
```

Default endpoint: `http://127.0.0.1:8010/v1`

## Smoke Test (CLI)

```bash
GSS_DEFAULT_ENDPOINT=http://127.0.0.1:8010/v1 gss your-store.myshopify.com describe
# Standard flow: verify identity then issue token
GSS_DEFAULT_ENDPOINT=http://127.0.0.1:8010/v1 gss your-store.myshopify.com auth verify-customer --order-id 1234567890 --email customer@example.com
GSS_DEFAULT_ENDPOINT=http://127.0.0.1:8010/v1 gss your-store.myshopify.com auth issue-token --verification-id <verification_id> --method api_key
GSS_DEFAULT_ENDPOINT=http://127.0.0.1:8010/v1 gss your-store.myshopify.com orders list
```

## Production Note

`ShopOwnedRuntimeAdapter` is intentionally local-dev. For production, replace it with your real webshop infrastructure (e.g. Redis/Postgres/KMS-backed auth + audit).
Legacy `auth login` is available for development only. Production integrations should use `verify-customer` + `issue-token`.
If the customer entered a wrong email and does not know `order_id`, this demo supports a phone recovery lookup path in `auth verify-customer --phone <number>`.
Read actions are guarded as well: `orders get` and `shipping track` validate `order_id` format and enforce customer ownership before returning data.
