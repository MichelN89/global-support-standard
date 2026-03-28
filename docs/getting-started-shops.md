# Getting Started: Make Your Shop GSS-Compatible

## Step 1: Install

```bash
pip install gss-provider-sdk gss-adapter-shopify   # or gss-adapter-woocommerce
```

## Step 2: Initialize

```bash
gss-init myshop
cd myshop-gss
```

## Step 3: Configure (Shopify example)

```python
from gss_provider import GSSProvider
from gss_adapter_shopify import ShopifyAdapter

provider = GSSProvider(
    shop_name="myshop.com",
    adapter=ShopifyAdapter(shop_url="https://myshop.myshopify.com", api_key="shpka_xxx"),
    protocols_dir="./protocols"
)
provider.serve(port=8080)
```

For custom platforms, implement domain classes. See [Full Spec](../spec/overview.md).

## Agent Delegation Quickstart (Recommended)

Use this default profile if your shop expects autonomous consumer agents or SaaS agents to act on behalf of customers.

1) Keep customer auth context short-lived and scoped:
- TTL: 5-60 minutes
- Scope by domain/action level (for example `orders:read`, `shipping:read`, `returns:request`)
- Bind auth artifacts to `GSS-Consumer-Id` where possible

2) Enforce these checks on every data-bearing endpoint:
- validate input identifiers server-side
- verify customer ownership/tenant scope before returning data
- fail closed on mismatch (`FORBIDDEN` / `VALIDATION_ERROR`)

3) Keep confirmation and verification strict:
- `request` actions: two-step confirmation
- `critical` actions: out-of-band verification (OTP/human approval)

4) Always capture audit metadata:
- customer id, consumer id/type, action, action level, parameters, result, request id

See [Agent Delegation Model](./agent-delegation-model.md) for full normative recommendations.

## Step 4: Write Protocols

Customize templates in `protocols/`. See [Protocol Format](../protocols/FORMAT.md).

## Step 5: Validate

```bash
gss validate localhost:8080 --level standard
```

## Step 6: Deploy

```bash
docker build -t myshop-gss . && docker run -p 8080:8080 --env-file .env myshop-gss
```

Make discoverable via `https://myshop.com/.well-known/gss.json` or DNS TXT record.

## Production Launch Checklist (First Real Tenant)

- [ ] Enforce required auth headers and consumer identity on protected endpoints.
- [ ] Enforce identifier validation + ownership checks on every data-bearing action.
- [ ] Use short-lived tokens (recommended 5-60 minutes) and least-privilege scopes.
- [ ] Enable two-step confirmation for `request` actions.
- [ ] Enforce out-of-band verification for `critical` actions.
- [ ] Configure CI required checks (`lint-ruff`, tests matrix, coverage, package-check, dependency-audit).
- [ ] Configure branch protection on `main` and enable CODEOWNERS.
- [ ] Publish and verify release artifacts from trusted source.
- [ ] Run a tenant-specific smoke test flow (`describe -> verify-customer -> issue-token -> orders/shipping`).
