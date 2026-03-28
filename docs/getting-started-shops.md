# Getting Started: Make Your Shop GSS-Compatible

## Step 1: Install

```bash
pip install global-support-standard
```

## Step 2: Run the reference provider (quick baseline)

```bash
gss-provider
```

Default endpoint: `http://127.0.0.1:8000/v1`

## Step 3: Integrate your own runtime adapter (production path)

Implement `ShopRuntimeAdapter` so your shop owns token issuance, confirmation storage, and audit persistence.

```python
from gss_provider.app import create_app
from gss_provider.contracts import ConfirmationRecord, IssuedToken, ShopRuntimeAdapter


class MyShopAdapter(ShopRuntimeAdapter):
    def issue_token(self, *, customer_id: str, method: str, ttl_seconds: int) -> IssuedToken:
        ...

    def resolve_customer(self, token: str) -> str | None:
        ...

    def create_confirmation(self, *, customer_id: str, payload: dict, ttl_seconds: int) -> ConfirmationRecord:
        ...

    def consume_confirmation(self, *, token: str, customer_id: str) -> ConfirmationRecord | None:
        ...

    def append_event(self, event: dict) -> None:
        ...

    def list_customer_events(self, customer_id: str) -> list[dict]:
        ...


app = create_app(adapter=MyShopAdapter())
```

Run with uvicorn:

```bash
uvicorn myshop_gss:app --host 0.0.0.0 --port 8080
```

For full contract guidance, see [Architecture](./architecture.md), [Authorization Model](./authorization-model.md), and [Full Spec](../spec/overview.md).

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

## Step 5: Validate (CI + conformance)

```bash
ruff check .
pytest --cov=src --cov-report=term-missing --cov-fail-under=80
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
