# Agent Delegation Model (Consumer and SaaS)

This document defines recommended implementation patterns for the GSS "act on behalf of customer" use case.

Primary perspective: autonomous consumer agents and SaaS support agents performing support actions safely against webshop GSS providers.

Related guidance:
- `docs/authorization-model.md`
- `docs/getting-started-shops.md`

## Scope

This is implementation guidance for adapter and provider authors.  
It does not change the core standard envelope or command model.

## Core Principle

Agents may automate support tasks, but data and actions must always remain:

- customer-authorized
- least-privilege scoped
- auditable
- fail-closed

## Actor Models

### 1) Direct Consumer Agent

- The customer uses their own AI/app/device agent.
- The agent obtains customer authorization context and calls the shop's GSS endpoint.

### 2) Delegated SaaS Agent

- A SaaS service acts for many tenants/customers.
- The SaaS agent is a distinct consumer and must identify itself with its own `GSS-Consumer-Id`.
- Webshop must still validate customer identity and token scope per request.

## Required Security Contract (MUST)

For every data-bearing or state-changing GSS call, providers MUST enforce:

1. **Authenticated context**
   - A valid customer authorization context is present.
2. **Consumer identity**
   - `GSS-Consumer-Id` and `GSS-Consumer-Type` are present and logged.
3. **Input validation**
   - Resource identifiers and sensitive parameters are validated server-side.
4. **Ownership/tenant checks**
   - Returned or modified resources belong to the authenticated customer scope.
5. **Fail-closed behavior**
   - On mismatch or uncertainty, return an error and do not return protected data.
6. **Audit logging**
   - Log request metadata and decision outcome for investigation and enforcement.

## Recommended Delegation Flow

### A) Agent-first session bootstrap (recommended)

1. Agent collects customer intent + minimal identity hints (`order_id`, email/phone).
2. Webshop verifies identity using its own mechanisms (OTP, signed session, existing login, KYC checks).
3. Webshop issues a short-lived scoped authorization context.
4. Agent performs GSS calls with that context.

### B) Token profile recommendations

- TTL: 5-60 minutes (short-lived by default)
- Narrow scopes by domain/action level (e.g. `orders:read`, `shipping:read`)
- Bind token to consumer identity where possible (`GSS-Consumer-Id`)
- Rotate/refresh with one-time semantics for long-running sessions

## Action-Level Policy Recommendations

| Action Level | Minimum recommended control |
|---|---|
| `read` | Auth + ownership checks + rate limits |
| `request` | Auth + ownership + two-step confirmation |
| `critical` | Auth + ownership + out-of-band verification + optional human approval |

## SaaS-on-behalf Guidance

When a SaaS agent acts for users:

- Keep consumer identity stable and unique (e.g. `support-squad-ai-prod`).
- Separate tenant contexts; never share customer auth artifacts across tenants.
- Use per-tenant keys/credentials and per-customer scoped sessions.
- Allow webshop-side revocation by consumer and by customer.
- Preserve end-user traceability in audit metadata.

## Error Semantics (recommended)

- `UNAUTHORIZED`: missing/invalid/expired auth context
- `MISSING_HEADERS`: missing consumer/version headers
- `VALIDATION_ERROR`: malformed resource identifiers or invalid input
- `FORBIDDEN`: customer does not own requested resource / insufficient scope
- `UPSTREAM_AUTH_ERROR`: provider adapter cannot authenticate against upstream platform

## Minimal Compliance Checklist for Agent Delegation

- [ ] Customer-bound auth context required for protected actions
- [ ] Consumer headers validated and logged
- [ ] Resource ID validation enforced server-side
- [ ] Ownership checks applied before data return
- [ ] Request/critical actions have confirmation or out-of-band controls
- [ ] Token TTL and scope restrictions implemented
- [ ] Revocation path exists for compromised consumer/customer sessions

## Production Baseline Profile (Recommended Defaults)

- Access token TTL: 15 minutes (max 60 minutes)
- Required headers on protected calls:
  - `Authorization`
  - `GSS-Consumer-Id`
  - `GSS-Consumer-Type`
  - `GSS-Version`
- Read-path controls: identifier validation + ownership checks + rate limits
- Request-path controls: two-step confirmation and audit event recording
- Critical-path controls: out-of-band verification and optional human approval

## Open-Source Boundary Reminder

GSS OSS should define and test the contract above.  
Each webshop adapter owns the concrete implementation details (IdP, OTP, session bridge, datastore, infra).
