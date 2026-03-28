# Authorization Model (Adapter-Agnostic)

This document defines a unified authorization contract for GSS providers, independent of platform-specific permission systems.

Related guidance:
- `docs/agent-delegation-model.md`
- `docs/getting-started-shops.md`

## Goals

- Keep GSS authorization portable across all adapters.
- Let each webshop keep its own internal scope/role model.
- Ensure consumers can discover and request the minimum required permissions.

## Core Principle

GSS standardizes **logical scopes** and action-level requirements.  
Adapters map those logical scopes to platform/internal permissions.

## GSS Logical Scopes

Scopes follow `<domain>:<level>` where level aligns with action classification.

Examples:

- `orders:read`
- `orders:request`
- `shipping:read`
- `returns:read`
- `returns:request`
- `account:read`
- `account:critical`
- `payments:read`
- `payments:request`

Providers MAY expose extra namespaced scopes:

- `shop:<domain>:<capability>`

Example: `shop:loyalty:redeem`.

## Required Rules For All Adapters

1. **Deny by default**  
   If an action has no satisfied required GSS scope, return authorization error.

2. **Least privilege**  
   Consumers should request only required scopes for intended actions.

3. **Action-level compatibility**  
   - `read` actions require corresponding `*:read`.
   - `request` actions require corresponding `*:request` (or stricter shop policy).
   - `critical` actions require corresponding `*:critical` plus any out-of-band requirements.

4. **Transparent mapping**  
   Adapter must implement and maintain mapping from GSS scopes to internal/platform permissions.

5. **Auditable decisions**  
   Authorization decisions must be loggable with scope inputs and decision outcome.

6. **Data exposure validation (required)**  
   Any action that can return customer or store data MUST:
   - require authenticated context,
   - validate resource identifiers (format and bounds),
   - enforce ownership/tenant checks before returning payload data,
   - fail closed (`FORBIDDEN` / `VALIDATION_ERROR`) on mismatch.

## Describe Contract (Authorization Metadata)

Providers SHOULD expose authorization metadata in top-level `describe`:

```json
{
  "authorization": {
    "gss_scopes_supported": [
      "orders:read",
      "orders:request",
      "shipping:read",
      "returns:read",
      "returns:request",
      "account:read"
    ],
    "scope_policy": {
      "deny_by_default": true,
      "least_privilege_required": true,
      "action_level_enforced": true
    },
    "scope_mapping_hints": [
      {
        "gss_scope": "orders:read",
        "adapter_scope": "adapter:orders:read",
        "note": "Adapter-local permission identifier; may map to platform OAuth scopes"
      }
    ],
    "custom_scopes": [
      "shop:loyalty:redeem"
    ]
  }
}
```

Notes:

- `scope_mapping_hints` is informative. Providers may omit sensitive internals.
- Internal permission model is adapter-owned and can vary by platform.

## Error Behavior

On insufficient scope:

- return `FORBIDDEN` (or `NOT_AUTHORIZED` depending provider policy),
- include machine-readable reason in `error.details`.

Suggested details:

```json
{
  "required_scopes": ["returns:request"],
  "granted_scopes": ["orders:read", "returns:read"],
  "action": "returns initiate"
}
```

## Certification Guidance

For a provider to be considered authorization-conformant:

- Required GSS scopes for implemented actions are declared.
- Scope checks are enforced at runtime.
- Data-bearing actions enforce input validation + ownership/tenant checks.
- Conformance tests demonstrate deny-by-default behavior.
- `describe` exposes machine-readable authorization metadata.

## Adapter Flexibility

Adapters may:

- implement stricter policies than baseline,
- require additional verification for sensitive actions,
- expose custom scopes.

Adapters must not:

- weaken required GSS action-level semantics,
- silently bypass scope enforcement for protected actions.
