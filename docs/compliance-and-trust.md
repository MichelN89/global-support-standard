# Compliance and Trust Boundary

GSS is a protocol standard and package ecosystem. It is not a centralized identity or persistence service.

## Responsibility Split

### GSS standard/packages are responsible for

- command structure and domain semantics
- required request headers and response envelope
- action-level behavior (read/request/critical semantics)
- protocol evaluation rules and validation contracts
- conformance test harness definitions

### Webshop implementations are responsible for

- issuing and validating customer auth tokens
- token revocation, expiry, and session security
- confirmation-token persistence and replay protection
- audit storage, retention, and legal compliance
- infrastructure hardening and operational controls
- browser CORS policy decisions (if browser clients are supported)

## Compliance Metadata

Shops should expose a `compliance` block in `describe`:

```json
{
  "compliance": {
    "level": "basic",
    "certified": false,
    "test_suite_version": "unverified",
    "responsibility_boundary": "GSS defines protocol contracts and validation. Shop implementations own token issuance, persistence, and audit infrastructure."
  }
}
```

Consumers should treat missing or uncertified compliance metadata as a risk signal.

## Consumer Behavior Guidance

- warn users when a shop is uncertified
- avoid implying that protocol conformance means infrastructure/security conformance
- keep high-impact actions behind explicit user confirmation

## Conformance Testing

Adapter contract tests are provided under `tests/conformance/` to verify expected behavior at the package boundary.  
Passing these tests does not replace production security audits.

## Reference Runtime Defaults

- Legacy login is disabled by default (`GSS_ENABLE_LEGACY_LOGIN=0`).
- Agent auth issuance is disabled by default (`GSS_ENABLE_AGENT_AUTH=0`) unless explicitly enabled by the shop.
- In-memory rate limiting is enabled by default (`GSS_RATE_LIMIT_ENABLED=1`) as a baseline guardrail.
