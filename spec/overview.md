# Global Support Standard (GSS)

**Document Type:** Open Standard Specification & Development Briefing
**Version:** 0.1 (Draft)
**Date:** 2026-03-28

---

## 1. What Is GSS?

The Global Support Standard is an open protocol that allows any webshop to expose its customer support operations in a machine-readable, standardized way — so that any AI agent, app, or device can provide complete self-service on behalf of the customer.

**The problem:** Customer support is fundamentally the same everywhere. A customer has a question about their order, wants to return something, needs a tracking update, or disputes a charge. The support agent follows a flowchart defined by the company. Every webshop reinvents this flowchart, trains humans to follow it, and builds proprietary systems around it.

**The insight:** If every webshop exposed its support operations and resolution protocols through a common standard, the entire human agent layer becomes optional. The customer's phone, browser, or AI assistant can talk directly to the shop.

**The vision:**

```
Today:
  Customer → Phone/Chat → Human Agent → Internal System → Resolution
  (minutes to days)

With GSS:
  Customer's Device → GSS Protocol → Shop's System → Resolution
  (seconds)
```

### 1.1 What GSS Is Not

- **Not a helpdesk platform.** GSS doesn't host tickets or manage agents. It's a protocol.
- **Not an API specification like OpenAPI.** OpenAPI describes any API. GSS specifically standardizes e-commerce support operations with built-in resolution logic.
- **Not tied to AI.** An AI agent can consume GSS, but so can a mobile app, a browser extension, or a smart speaker. The consumer doesn't matter — the standard is the same.

### 1.2 How It Works (30-Second Version)

```bash
# 1. Discover what a shop supports
$ gss amazon.com describe
{
  "shop": "amazon.com",
  "version": "1.0",
  "domains": ["orders", "returns", "shipping", "products", "account", "payments"],
  "auth_methods": ["oauth2", "api_key"]
}

# 2. Authenticate as a customer
$ gss amazon.com auth login --method oauth2
→ Opens browser, customer logs in, token stored

# 3. Interact
$ gss amazon.com orders list
$ gss amazon.com orders get --id 408-1234567-8901234
$ gss amazon.com returns check-eligibility --order-id 408-1234567-8901234 --item-id B09V3KXJPB
$ gss amazon.com returns initiate --order-id 408-1234567-8901234 --item-id B09V3KXJPB --reason "defective"

# 4. Follow resolution protocol (the shop's rules, not the AI's judgment)
$ gss amazon.com protocols get --trigger "return-request" --context '{"order_age_days": 12}'
→ Returns the shop's decision tree for this scenario
```

---

## 2. Architecture

### 2.1 The Three Layers

```
┌─────────────────────────────────────────────────────────────┐
│ CONSUMER LAYER                                               │
│  Any app, device, or AI agent that speaks GSS                │
│                                                              │
│  Examples:                                                   │
│  - Support Squad AI (AI support agent)                       │
│  - Customer's phone (GSS app)                                │
│  - Browser extension ("manage my orders")                    │
│  - Smart speaker ("where's my package?")                     │
│  - Chatbot on the shop's website                             │
└──────────────────────┬──────────────────────────────────────┘
                       │ GSS Protocol (CLI or HTTP)
                       │ Authenticated as the customer
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ GSS STANDARD                                                 │
│                                                              │
│  - Standardized command structure                            │
│  - Domain definitions (orders, returns, shipping, ...)       │
│  - Resolution protocols (the shop's flowcharts)              │
│  - Discovery via "describe"                                  │
│  - Auth via OAuth2 / API key                                 │
│                                                              │
│  The contract between consumers and shops.                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ SHOP LAYER                                                   │
│  Each shop implements a GSS provider                         │
│                                                              │
│  - Connects to the shop's existing systems (Shopify,         │
│    WooCommerce, custom, etc.)                                │
│  - Maps internal operations to GSS commands                  │
│  - Defines resolution protocols for their policies           │
│  - Publishes a describe manifest                             │
│                                                              │
│  Examples:                                                   │
│  - gss-provider-shopify (open-source package)                │
│  - gss-provider-woocommerce                                  │
│  - amazon.com's custom GSS implementation                    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Command Structure

Every GSS command follows the same pattern:

```
gss <shop> <domain> <action> [--flags]
```

Examples:

```
gss coolblue.nl orders get --id ORD-12345
gss bol.com returns initiate --order-id 9876 --item-id ABC --reason "wrong_size"
gss zalando.de shipping track --order-id 5555
gss amazon.com protocols get --trigger "delivery-not-received" --context '{"days_since_expected": 3}'
```

The `<shop>` identifier is a domain name. Shops register their GSS endpoint, and the CLI resolves it (via DNS TXT record, `.well-known/gss.json`, or a central registry).

### 2.3 Discovery

Every GSS provider MUST implement `describe` at multiple levels:

```bash
# Top-level: what does this shop support?
$ gss coolblue.nl describe
{
  "shop": "coolblue.nl",
  "name": "Coolblue",
  "gss_version": "1.0",
  "domains": ["orders", "returns", "shipping", "products", "account", "payments"],
  "auth_methods": ["oauth2"],
  "endpoint": "https://gss.coolblue.nl/v1"
}

# Domain-level: what can I do with orders?
$ gss coolblue.nl orders describe
{
  "domain": "orders",
  "commands": [
    {
      "name": "orders get",
      "description": "Get full order details including items, status, and timeline",
      "parameters": [
        {"name": "id", "type": "string", "required": true, "description": "Order ID"}
      ]
    },
    {
      "name": "orders list",
      "description": "List customer's orders with optional filters",
      "parameters": [
        {"name": "status", "type": "string", "required": false, "description": "Filter: pending, shipped, delivered, cancelled"},
        {"name": "since", "type": "string", "required": false, "description": "ISO date — only orders after this date"},
        {"name": "limit", "type": "integer", "required": false, "description": "Max results (default 20)"}
      ]
    }
  ]
}
```

This is the same `--describe` pattern from Support Squad AI, but scoped per shop and per domain.

### 2.4 Authentication

GSS uses customer-level auth, not shop-level. The consumer (app/AI/device) authenticates as the customer, not as a support agent.

**Required:** Every GSS provider must support at least one of:

| Method     | Use Case                                        | Flow                                              |
|------------|------------------------------------------------|----------------------------------------------------|
| `oauth2`   | Browser-based apps, AI agents with user consent | Standard OAuth2 authorization code flow            |
| `api_key`  | Server-to-server, pre-authorized integrations   | Customer generates a key in their account settings |

**Auth context travels with every request:**

```bash
$ gss coolblue.nl auth login --method oauth2
# → Browser opens, customer logs in, token stored locally

$ gss coolblue.nl orders list
# → Token automatically attached to request
```

AI agents like Support Squad AI would use `api_key` — the tenant configures their GSS credentials once, and the agent uses them for all interactions.

Authorization scope design and adapter flexibility rules are defined in `docs/authorization-model.md`.

### 2.5 Channels

GSS providers MAY expose one or more sales/service channels (for example `web`, `marketplace-eu`, `email`).

- Consumers MAY pass `channel` on domain commands.
- Providers with a single channel SHOULD auto-resolve that channel.
- Providers with multiple channels MUST either:
  - resolve deterministically from request context (for example `order_id`), or
  - return a validation error requiring explicit `channel`.
- If a channel is resolved or used, providers SHOULD include `meta.channel` in the response envelope.

### 2.6 Describe Auth Levels and Menu

`GET /describe` supports auth-aware visibility:

- `none`: unauthenticated caller receives minimum discovery payload (`shop`, `name`, `gss_version`, `auth_methods`, `endpoint`).
- `agent`: trusted agent session can receive expanded metadata.
- `customer`: customer-authenticated session can receive full metadata.

Providers SHOULD publish an auth menu in `auth_methods` and metadata for:

- `agent_key`
- `oauth2`
- `api_key`
- `customer_verify`

`auth login` remains available for backward compatibility but SHOULD be marked deprecated.

### 2.7 Customer Verification Field Options

Providers MAY support different verification combinations and SHOULD declare accepted combinations in describe metadata.

Common fields:

- `order_id`
- `email`
- `phone`
- `postal_code`
- `last_name`

Verification and token issuance are two distinct steps:

1. `auth verify-customer` -> returns `verification_id`
2. `auth issue-token` -> exchanges `verification_id` for a short-lived customer token

### 2.8 Compliance Model

GSS uses RFC 2119 semantics:

- **MUST**: required for conformant implementations.
- **SHOULD**: strong recommendation; deviations should be documented.
- **RECOMMENDED**: useful interoperability guidance with lower conformance impact.

Providers SHOULD expose compliance metadata in describe, including:

- `level` (`basic`, `standard`, `complete`)
- `certified` (boolean)
- `test_suite_version`
- `responsibility_boundary`

---

## 3. Core Domains

Every GSS provider implements some or all of these domains. The `describe` response tells the consumer which are available.

The standard defines **required commands** (must implement if the domain is supported) and **optional commands** (extend functionality).

---

### 3.1 Orders

The most fundamental domain. Almost every support inquiry starts with an order.

**Required commands:**

```
gss <shop> orders get --id <order_id>
```

Returns complete order details:

```json
{
  "id": "ORD-12345",
  "status": "shipped",
  "placed_at": "2026-03-20T14:30:00Z",
  "total": {"amount": 79.99, "currency": "EUR"},
  "items": [
    {
      "id": "ITEM-001",
      "product_id": "SKU-ABC",
      "name": "Wireless Headphones",
      "quantity": 1,
      "price": {"amount": 79.99, "currency": "EUR"},
      "status": "shipped"
    }
  ],
  "shipping": {
    "method": "Standard",
    "address": {"city": "Leeuwarden", "country": "NL"},
    "tracking": {"carrier": "PostNL", "tracking_id": "3SPOST1234567", "url": "https://..."},
    "estimated_delivery": "2026-03-25",
    "shipped_at": "2026-03-21T09:00:00Z"
  },
  "payment": {
    "method": "iDEAL",
    "status": "paid",
    "paid_at": "2026-03-20T14:31:00Z"
  },
  "timeline": [
    {"event": "placed", "at": "2026-03-20T14:30:00Z"},
    {"event": "payment_confirmed", "at": "2026-03-20T14:31:00Z"},
    {"event": "shipped", "at": "2026-03-21T09:00:00Z"}
  ]
}
```

```
gss <shop> orders list [--status <status>] [--since <date>] [--limit <n>]
```

Returns summary list of customer's orders.

**Optional commands:**

```
gss <shop> orders cancel --id <order_id> [--reason <text>]
gss <shop> orders modify --id <order_id> --changes <json>
gss <shop> orders reorder --id <order_id>
```

**Standard order statuses:** `pending`, `confirmed`, `processing`, `shipped`, `out_for_delivery`, `delivered`, `cancelled`, `returned`, `refunded`.

Every shop MUST use these status values. They may add custom sub-statuses in a `status_detail` field but the top-level `status` must be from this list.

---

### 3.2 Returns & Refunds

**Required commands:**

```
gss <shop> returns check-eligibility --order-id <id> --item-id <id>
```

Returns whether the item can be returned, why or why not, and the available return options. This is the **recommended first step in any return flow** — but `initiate` MUST re-validate server-side regardless (never trust that the consumer checked first).

```json
{
  "eligible": true,
  "item": {"id": "ITEM-001", "name": "Wireless Headphones"},
  "return_window": {"opens": "2026-03-25", "closes": "2026-04-25", "days_remaining": 28},
  "options": [
    {
      "type": "return_for_refund",
      "refund_method": "original_payment",
      "refund_amount": {"amount": 79.99, "currency": "EUR"},
      "shipping_cost": "free",
      "label_provided": true
    },
    {
      "type": "exchange",
      "exchange_for": ["same_product_different_color", "same_product_different_size"],
      "shipping_cost": "free"
    }
  ],
  "reasons_accepted": ["defective", "wrong_item", "not_as_described", "changed_mind", "wrong_size", "wrong_color", "arrived_too_late", "other"]
}
```

If not eligible:

```json
{
  "eligible": false,
  "reason": "return_window_closed",
  "return_window": {"opened": "2026-01-15", "closed": "2026-02-15"},
  "alternatives": ["Contact support for exceptional cases"]
}
```

**Implementation rule:** `initiate` MUST always re-validate eligibility server-side. A consumer can skip `check-eligibility` and call `initiate` directly — the shop must reject ineligible returns regardless. The eligibility check is a convenience for the consumer, not a security gate.

```
gss <shop> returns initiate --order-id <id> --item-id <id> --reason <reason> [--option <type>]
```

This is a `request`-level action — two-step confirmation required. After confirmation, returns a return ID, instructions, shipping label, and the refund's initial status.

```json
{
  "return_id": "RET-789",
  "status": "initiated",
  "instructions": [
    "Pack the item in its original packaging.",
    "Attach the shipping label below.",
    "Drop off at any PostNL location."
  ],
  "label": {
    "url": "https://shop.com/returns/RET-789/label.pdf",
    "carrier": "PostNL",
    "drop_off_locations_url": "https://postnl.nl/locations"
  },
  "refund": {
    "status": "awaiting_return",
    "method": "original_payment",
    "amount": {"amount": 79.99, "currency": "EUR"},
    "note": "Refund will be processed after we receive and inspect the item. This typically takes up to 14 business days after receipt."
  }
}
```

Note: the refund status starts as `awaiting_return` — NOT `processing`. The money doesn't move until the warehouse confirms.

```
gss <shop> returns status --return-id <id>
```

Returns the full return status with a timeline and nested refund status. This is what the customer sees when they ask "where's my return?"

**Example: return in transit (customer shipped it back, warehouse hasn't received it yet)**

```json
{
  "return_id": "RET-789",
  "status": "in_transit",
  "timeline": [
    {"event": "initiated", "at": "2026-01-15T10:00:00Z"},
    {"event": "label_generated", "at": "2026-01-15T10:00:05Z"},
    {"event": "in_transit", "at": "2026-01-17T14:00:00Z", "detail": "Picked up by PostNL"}
  ],
  "tracking": {
    "carrier": "PostNL",
    "tracking_id": "3SPOST9876543",
    "tracking_url": "https://postnl.nl/track/3SPOST9876543"
  },
  "refund": {
    "status": "awaiting_return",
    "amount": {"amount": 79.99, "currency": "EUR"},
    "method": "original_payment"
  }
}
```

**Example: warehouse received, inspecting**

```json
{
  "return_id": "RET-789",
  "status": "inspecting",
  "timeline": [
    {"event": "initiated", "at": "2026-01-15T10:00:00Z"},
    {"event": "label_generated", "at": "2026-01-15T10:00:05Z"},
    {"event": "in_transit", "at": "2026-01-17T14:00:00Z"},
    {"event": "received", "at": "2026-01-21T09:30:00Z"},
    {"event": "inspecting", "at": "2026-01-21T09:35:00Z"}
  ],
  "refund": {
    "status": "awaiting_inspection",
    "amount": {"amount": 79.99, "currency": "EUR"},
    "method": "original_payment",
    "inspection_sla_days": 14,
    "estimated_by": "2026-02-04"
  }
}
```

**Example: inspection approved, refund processing**

```json
{
  "return_id": "RET-789",
  "status": "approved",
  "timeline": [
    {"event": "initiated", "at": "2026-01-15T10:00:00Z"},
    {"event": "received", "at": "2026-01-21T09:30:00Z"},
    {"event": "inspecting", "at": "2026-01-21T09:35:00Z"},
    {"event": "approved", "at": "2026-01-28T11:00:00Z"}
  ],
  "refund": {
    "status": "processing",
    "amount": {"amount": 79.99, "currency": "EUR"},
    "method": "original_payment",
    "estimated_completion": "2026-02-02"
  }
}
```

**Example: refund completed**

```json
{
  "return_id": "RET-789",
  "status": "refunded",
  "timeline": [
    {"event": "initiated", "at": "2026-01-15T10:00:00Z"},
    {"event": "received", "at": "2026-01-21T09:30:00Z"},
    {"event": "approved", "at": "2026-01-28T11:00:00Z"},
    {"event": "refunded", "at": "2026-01-30T15:00:00Z"}
  ],
  "refund": {
    "status": "completed",
    "amount": {"amount": 79.99, "currency": "EUR"},
    "method": "iDEAL",
    "completed_at": "2026-01-30T15:00:00Z"
  }
}
```

**Example: inspection rejected (item damaged by customer, not eligible)**

```json
{
  "return_id": "RET-789",
  "status": "rejected",
  "timeline": [
    {"event": "initiated", "at": "2026-01-15T10:00:00Z"},
    {"event": "received", "at": "2026-01-21T09:30:00Z"},
    {"event": "inspecting", "at": "2026-01-21T09:35:00Z"},
    {"event": "rejected", "at": "2026-01-25T14:00:00Z"}
  ],
  "rejection": {
    "reason": "Item shows signs of use beyond normal inspection. The screen has scratches inconsistent with shipping damage.",
    "policy_reference": "Items must be in original, unused condition for a full refund.",
    "options": [
      {
        "type": "return_to_customer",
        "description": "We'll ship the item back to you at no cost.",
        "command": "gss shop.com returns request-return-back --return-id RET-789"
      },
      {
        "type": "partial_refund",
        "description": "We can offer a 50% partial refund and keep the item.",
        "refund_amount": {"amount": 39.99, "currency": "EUR"},
        "command": "gss shop.com returns accept-partial --return-id RET-789 --option partial_refund"
      },
      {
        "type": "dispute",
        "description": "If you disagree with our assessment, you can dispute this decision.",
        "command": "gss shop.com returns dispute --return-id RET-789 --reason <text>"
      }
    ]
  },
  "refund": {
    "status": "rejected",
    "reason": "inspection_failed"
  }
}
```

```
gss <shop> returns list [--status <status>] [--since <date>]
```

**Optional commands:**

```
gss <shop> returns cancel --return-id <id>
gss <shop> returns dispute --return-id <id> --reason <text>
gss <shop> returns request-return-back --return-id <id>
gss <shop> returns accept-partial --return-id <id> --option <type>
gss <shop> refunds status --refund-id <id>
gss <shop> refunds list [--since <date>]
```

**Standard return statuses:** `initiated`, `label_generated`, `in_transit`, `received`, `inspecting`, `approved`, `refunded`, `rejected`, `disputed`.

**Standard refund statuses** (nested within a return):

```
awaiting_return → awaiting_inspection → processing → completed
                                                   ↘ partially_refunded
                  ↘ rejected (inspection failed)
```

| Refund Status           | Meaning                                                         |
|-------------------------|-----------------------------------------------------------------|
| `awaiting_return`       | Return initiated, item not yet received by warehouse            |
| `awaiting_inspection`   | Item received, warehouse is inspecting                          |
| `processing`            | Inspection approved, refund is being processed to payment method|
| `completed`             | Money returned to customer                                      |
| `partially_refunded`    | Partial refund issued (e.g., after negotiation on rejected item)|
| `rejected`              | Inspection failed, no refund issued                             |

The refund status tells the customer exactly where their money is in the pipeline. Combined with `inspection_sla_days` and `estimated_by`, the consumer can give precise answers to "where's my refund?" without guessing.

---

### 3.3 Shipping & Delivery

**Required commands:**

```
gss <shop> shipping track --order-id <id>
```

```json
{
  "order_id": "ORD-12345",
  "carrier": "PostNL",
  "tracking_id": "3SPOST1234567",
  "tracking_url": "https://postnl.nl/track/3SPOST1234567",
  "status": "in_transit",
  "estimated_delivery": "2026-03-25",
  "events": [
    {"status": "picked_up", "at": "2026-03-21T09:00:00Z", "location": "Warehouse Amsterdam"},
    {"status": "in_transit", "at": "2026-03-22T06:00:00Z", "location": "Sorting center Utrecht"},
    {"status": "out_for_delivery", "at": "2026-03-25T08:00:00Z", "location": "Leeuwarden"}
  ]
}
```

```
gss <shop> shipping report-issue --order-id <id> --issue <type>
```

Issue types: `not_received`, `damaged`, `wrong_item`, `partial_delivery`, `delivered_to_wrong_address`.

Returns the shop's resolution for this specific issue (using protocols — see Section 4).

**Optional commands:**

```
gss <shop> shipping change-address --order-id <id> --address <json>
gss <shop> shipping request-redelivery --order-id <id> [--date <date>]
gss <shop> shipping delivery-preferences --set <json>
```

**Standard shipping statuses:** `pending`, `processing`, `picked_up`, `in_transit`, `out_for_delivery`, `delivered`, `failed_delivery`, `returned_to_sender`.

---

### 3.4 Products

**Required commands:**

```
gss <shop> products get --id <product_id>
```

```json
{
  "id": "SKU-ABC",
  "name": "Wireless Headphones XM5",
  "description": "Noise-cancelling wireless headphones...",
  "price": {"amount": 79.99, "currency": "EUR"},
  "availability": "in_stock",
  "estimated_delivery": "2026-03-26",
  "variants": [
    {"id": "SKU-ABC-BLK", "color": "Black", "availability": "in_stock"},
    {"id": "SKU-ABC-WHT", "color": "White", "availability": "out_of_stock"}
  ],
  "warranty": {
    "duration_months": 24,
    "type": "manufacturer",
    "claim_url": "https://shop.com/warranty"
  }
}
```

```
gss <shop> products search --query <text> [--category <cat>] [--limit <n>]
```

**Optional commands:**

```
gss <shop> products check-availability --id <id> [--postal-code <code>]
gss <shop> products warranty-status --id <id> --purchase-date <date>
gss <shop> products notify-restock --id <id> --email <email>
gss <shop> products compare --ids <id1,id2,id3>
```

---

### 3.5 Account

**Required commands:**

```
gss <shop> account get
```

Returns the authenticated customer's account details.

```json
{
  "id": "CUST-456",
  "email": "jan@example.nl",
  "name": "Jan de Vries",
  "phone": "+31612345678",
  "addresses": [
    {
      "id": "ADDR-1",
      "type": "shipping",
      "default": true,
      "line1": "Nieuwestad 100",
      "city": "Leeuwarden",
      "postal_code": "8911 CL",
      "country": "NL"
    }
  ],
  "created_at": "2024-06-15T10:00:00Z"
}
```

```
gss <shop> account update --changes <json>
```

For non-sensitive fields: name, phone, preferences. **Cannot be used to change email.** If `email` is included in `--changes`, the shop MUST reject with error `USE_CHANGE_EMAIL_FLOW`:

```json
{
  "status": "error",
  "error": {
    "code": "USE_CHANGE_EMAIL_FLOW",
    "message": "Email cannot be changed via account update. Use 'account change-email' instead.",
    "action": "update"
  }
}
```

```
gss <shop> account addresses list
gss <shop> account addresses add --address <json>
gss <shop> account addresses update --id <id> --changes <json>
gss <shop> account addresses delete --id <id>
```

#### Email Change Flow

Email is the identity anchor — it controls login, password resets, and order notifications. Changing it is the most sensitive account operation. GSS defines two paths: the **standard flow** (customer has access to current email) and the **recovery flow** (customer cannot access current email).

##### Standard Flow (access to current email)

```
gss <shop> account change-email --new-email <email>
```

This is a **`critical`-level action** with a unique three-step flow:

**Step 1: Request (consumer calls the command)**

```bash
$ gss shop.com account change-email --new-email jan.new@example.nl
```

Response:

```json
{
  "status": "verification_required",
  "change_request_id": "ECH-001",
  "steps_required": [
    {
      "step": 1,
      "type": "verify_current_email",
      "email_hint": "j***@example.nl",
      "message": "A verification code has been sent to your current email address."
    },
    {
      "step": 2,
      "type": "verify_new_email",
      "email_hint": "j***.new@example.nl",
      "message": "After verifying your current email, a code will be sent to your new address."
    }
  ],
  "alternative_flow": {
    "available": true,
    "message": "Can't access your current email? Use 'account change-email-recover' instead.",
    "command": "gss shop.com account change-email-recover --new-email jan.new@example.nl"
  },
  "expires_at": "2026-03-28T11:30:00Z"
}
```

The shop sends an OTP to the **current** email address. No changes happen yet.

**Step 2: Verify current email**

```bash
$ gss shop.com account change-email-verify --change-request-id ECH-001 --step 1 --code 847291
```

Response:

```json
{
  "status": "step_1_verified",
  "message": "Current email verified. A verification code has now been sent to jan.new@example.nl."
}
```

Only after verifying the old email does the shop send an OTP to the new email. This prevents an attacker who has the new inbox from completing the flow without access to the old inbox.

**Step 3: Verify new email**

```bash
$ gss shop.com account change-email-verify --change-request-id ECH-001 --step 2 --code 563108
```

Response:

```json
{
  "status": "completed",
  "message": "Email successfully changed to jan.new@example.nl.",
  "old_email": "jan@example.nl",
  "new_email": "jan.new@example.nl",
  "notification_sent_to_old_email": true
}
```

The shop sends a notification to the **old** email: "Your email was changed to j***.new@example.nl. If this wasn't you, contact us immediately." This is the last line of defense. (If the old email was a typo, nobody receives this — that's fine.)

##### Recovery Flow (no access to current email)

For cases where the customer made a typo during registration, lost access to their email provider, or their email account was compromised. This flow uses phone/SMS verification as the alternative identity proof.

**Prerequisite:** The customer must have a phone number on file. If they don't, this flow is unavailable and the shop must offer a manual identity verification process (outside GSS — e.g., upload ID document via the shop's website).

```
gss <shop> account change-email-recover --new-email <email>
```

**Step 1: Request recovery**

```bash
$ gss shop.com account change-email-recover --new-email jan.correct@example.nl
```

Response:

```json
{
  "status": "recovery_verification_required",
  "change_request_id": "ECH-002",
  "verification_method": "phone",
  "phone_hint": "+316****5678",
  "steps_required": [
    {
      "step": 1,
      "type": "verify_phone",
      "methods_available": ["sms", "call"],
      "message": "To verify your identity, we'll send a code to the phone number on your account."
    },
    {
      "step": 2,
      "type": "verify_identity_questions",
      "message": "After phone verification, you'll need to answer security questions to confirm your identity."
    },
    {
      "step": 3,
      "type": "verify_new_email",
      "message": "Finally, a code will be sent to your new email address."
    }
  ],
  "no_phone_on_file": false,
  "expires_at": "2026-03-28T11:30:00Z"
}
```

If no phone on file:

```json
{
  "status": "recovery_not_available",
  "no_phone_on_file": true,
  "message": "No phone number is registered on your account. Please contact support directly for manual identity verification.",
  "manual_verification_url": "https://shop.com/support/identity-verification"
}
```

**Step 2: Choose SMS or call, then verify**

```bash
$ gss shop.com account change-email-recover-verify --change-request-id ECH-002 --step 1 --method sms
```

Shop sends SMS to the phone number on file. Customer enters the code:

```bash
$ gss shop.com account change-email-recover-verify --change-request-id ECH-002 --step 1 --code 739201
```

```json
{
  "status": "step_1_verified",
  "message": "Phone verified. Please answer the following security questions."
}
```

**Step 3: Identity verification questions**

The shop asks questions only the real account owner would know — based on order history, account activity, and registration details.

```bash
$ gss shop.com account change-email-recover-verify --change-request-id ECH-002 --step 2
```

```json
{
  "status": "questions_required",
  "questions": [
    {"id": "q1", "question": "What was your most recent order (approximate date or product)?"},
    {"id": "q2", "question": "What payment method is on your account?"},
    {"id": "q3", "question": "What is the shipping address on your account (city is enough)?"}
  ]
}
```

```bash
$ gss shop.com account change-email-recover-verify --change-request-id ECH-002 --step 2 \
    --answers '{"q1": "headphones last week", "q2": "iDEAL", "q3": "Leeuwarden"}'
```

The shop evaluates the answers with fuzzy matching (not exact string match — "last week" is close enough if there was an order 5 days ago). If sufficient answers are correct:

```json
{
  "status": "step_2_verified",
  "message": "Identity verified. A verification code has been sent to jan.correct@example.nl."
}
```

If answers are insufficient:

```json
{
  "status": "step_2_failed",
  "attempts_remaining": 1,
  "message": "We couldn't verify your identity. Please try again or contact support for manual verification.",
  "manual_verification_url": "https://shop.com/support/identity-verification"
}
```

**Step 4: Verify new email**

Same as the standard flow — OTP to the new email address:

```bash
$ gss shop.com account change-email-recover-verify --change-request-id ECH-002 --step 3 --code 482910
```

```json
{
  "status": "completed",
  "message": "Email successfully changed to jan.correct@example.nl.",
  "old_email": "jan@exmple.nl",
  "new_email": "jan.correct@example.nl",
  "notification_sent_to_old_email": true,
  "notification_sent_to_phone": true
}
```

Notifications go to both the old email (even if it's a typo — someone might receive it) AND the phone via SMS, confirming the change was made.

##### Security rules for email change (both flows)

**Standard flow:**
- Both verifications must complete within 30 minutes.
- After 3 failed OTP attempts on either step, the change request is cancelled.
- The change request ID is single-use.

**Recovery flow (additional restrictions because it bypasses email verification):**
- Phone OTP + identity questions + new email OTP — all three must pass. Two out of three is not enough.
- Maximum 2 recovery attempts per account per 24 hours. After that, account is temporarily locked for email changes and the shop must notify the customer via SMS.
- Identity questions must be drawn from at least 3 different data sources (order history, payment method, address, registration date, etc.). The shop MUST NOT use information that is easily available publicly (e.g., full name alone is not sufficient).
- After a successful recovery flow, the shop SHOULD enforce a 24-hour cooling period before allowing another email change — prevents rapid chain-changes by an attacker who got through once.
- The shop must log the recovery with: old email, new email, phone number used, IP address, consumer ID, which questions were asked and answered, timestamps of all verification steps.

**Both flows:**
- AI agents (`consumer_type: ai_agent`) CANNOT initiate email changes — this is enforced by the standard, not just by shop policy. Only `app` and `device` consumer types can initiate these flows, because the customer must directly receive and enter OTP codes.
- The shop must log all email changes in the audit trail.

**Optional commands:**

```
gss <shop> account payment-methods list
gss <shop> account payment-methods add --method <json>
gss <shop> account payment-methods delete --id <id>
gss <shop> account delete-request
gss <shop> account export-data
gss <shop> account audit-log [--since <date>] [--limit <n>]
```

---

### 3.6 Payments & Invoices

**Required commands:**

```
gss <shop> payments get --order-id <id>
```

```json
{
  "order_id": "ORD-12345",
  "payments": [
    {
      "id": "PAY-001",
      "method": "iDEAL",
      "amount": {"amount": 79.99, "currency": "EUR"},
      "status": "paid",
      "paid_at": "2026-03-20T14:31:00Z"
    }
  ]
}
```

```
gss <shop> payments invoice --order-id <id>
```

Returns invoice PDF URL or structured invoice data.

**Optional commands:**

```
gss <shop> payments dispute --order-id <id> --reason <text>
gss <shop> payments retry --order-id <id>
gss <shop> payments list [--since <date>] [--status <status>]
```

**Standard payment statuses:** `pending`, `paid`, `failed`, `refunded`, `partially_refunded`, `disputed`.

---

### 3.7 Subscriptions

**Required commands (if shop has subscriptions):**

```
gss <shop> subscriptions list
gss <shop> subscriptions get --id <id>
```

```json
{
  "id": "SUB-100",
  "product": "Coffee Beans Monthly Box",
  "status": "active",
  "billing_cycle": "monthly",
  "next_billing_date": "2026-04-01",
  "price": {"amount": 24.99, "currency": "EUR"},
  "created_at": "2025-09-01T00:00:00Z",
  "can_pause": true,
  "can_cancel": true,
  "cancel_notice_days": 0
}
```

```
gss <shop> subscriptions pause --id <id> [--until <date>]
gss <shop> subscriptions resume --id <id>
gss <shop> subscriptions cancel --id <id> [--reason <text>]
```

**Optional commands:**

```
gss <shop> subscriptions modify --id <id> --changes <json>
gss <shop> subscriptions skip-next --id <id>
gss <shop> subscriptions change-frequency --id <id> --cycle <weekly|monthly|quarterly>
```

**Standard subscription statuses:** `active`, `paused`, `cancelled`, `past_due`, `expired`.

---

### 3.8 Loyalty & Points

**Required commands (if shop has loyalty program):**

```
gss <shop> loyalty balance
```

```json
{
  "program_name": "Coolblue Points",
  "points_balance": 2450,
  "points_value": {"amount": 24.50, "currency": "EUR"},
  "tier": "Gold",
  "next_tier": {"name": "Platinum", "points_needed": 550},
  "points_expiring": {"amount": 200, "expires_at": "2026-06-30"}
}
```

```
gss <shop> loyalty history [--since <date>] [--limit <n>]
```

```
gss <shop> loyalty redeem --points <n> --order-id <id>
```

**Optional commands:**

```
gss <shop> loyalty rewards list
gss <shop> loyalty rewards redeem --reward-id <id>
gss <shop> loyalty tier-benefits
```

---

### 3.9 Action Level Classification (Security Reference)

Every command has a fixed action level that determines what authentication is required. Shops can upgrade a level (make it stricter) but NEVER downgrade.

| Domain        | Command                       | Level      | Notes                                      |
|---------------|-------------------------------|------------|--------------------------------------------|
| orders        | get, list                     | `read`     |                                            |
| orders        | cancel, modify                | `request`  | Two-step confirmation required             |
| orders        | reorder                       | `request`  |                                            |
| returns       | check-eligibility, status, list | `read`   |                                            |
| returns       | initiate                      | `request`  | Two-step confirmation required             |
| returns       | cancel                        | `request`  |                                            |
| returns       | accept-partial                | `request`  | Two-step confirmation required             |
| returns       | dispute                       | `request`  |                                            |
| returns       | request-return-back           | `request`  |                                            |
| shipping      | track                         | `read`     |                                            |
| shipping      | report-issue                  | `request`  |                                            |
| shipping      | change-address                | `request`  |                                            |
| products      | get, search, check-availability | `read`   |                                            |
| products      | notify-restock                | `read`     | Only subscribes to notification            |
| account       | get, addresses list           | `read`     |                                            |
| account       | update (name, phone, prefs)   | `request`  | Cannot change email via this command       |
| account       | addresses add/update          | `request`  |                                            |
| account       | addresses delete              | `request`  |                                            |
| account       | change-email                  | `critical` | Standard flow — dual-email OTP. AI agents BLOCKED. |
| account       | change-email-verify           | `critical` | Part of standard email change flow         |
| account       | change-email-recover          | `critical` | Recovery flow — phone + identity questions + new email OTP. AI agents BLOCKED. |
| account       | change-email-recover-verify   | `critical` | Part of recovery flow                      |
| account       | payment-methods list          | `read`     |                                            |
| account       | payment-methods add/delete    | `critical` | Out-of-band OTP required                  |
| account       | delete-request                | `critical` | Out-of-band OTP required                  |
| account       | export-data, audit-log        | `read`     |                                            |
| payments      | get, invoice, list            | `read`     |                                            |
| payments      | dispute                       | `request`  |                                            |
| payments      | retry                         | `request`  |                                            |
| refunds       | status, list                  | `read`     |                                            |
| refunds       | force                         | `critical` | Override normal flow — OTP required        |
| subscriptions | list, get                     | `read`     |                                            |
| subscriptions | pause, resume, skip-next      | `request`  |                                            |
| subscriptions | cancel                        | `request`  |                                            |
| subscriptions | modify, change-frequency      | `request`  |                                            |
| loyalty       | balance, history, tier-benefits | `read`   |                                            |
| loyalty       | redeem, rewards redeem        | `request`  | Two-step confirmation required             |
| protocols     | get                           | `read`     | Reading a protocol is always safe          |

---

## 4. Resolution Protocols

This is what makes GSS more than just an API. **Resolution protocols are the shop's support flowcharts, expressed as machine-readable rules.**

When a customer has an issue, the consumer (AI/app/device) doesn't decide what to do — it asks the shop's protocols what the correct resolution is, given the context.

### 4.1 How Protocols Work

```
gss <shop> protocols get --trigger <trigger> --context <json>
```

The consumer sends:
- A **trigger** — what happened (e.g., `delivery-not-received`, `return-request`, `order-cancel-request`)
- A **context** — facts about the situation (e.g., how many days since expected delivery, order value, customer tier)

The shop returns:
- A **resolution** — what to do (e.g., offer reshipment, refund, tell customer to wait)
- **Actions** — specific GSS commands to execute if the customer agrees
- **Conditions** — what determines which resolution applies

### 4.2 Protocol Response Format

```bash
$ gss coolblue.nl protocols get \
    --trigger "delivery-not-received" \
    --context '{"order_id": "ORD-12345", "days_since_expected": 3}'
```

```json
{
  "trigger": "delivery-not-received",
  "context_received": {
    "order_id": "ORD-12345",
    "days_since_expected": 3
  },
  "context_enriched": {
    "order_value": 79.99,
    "carrier": "PostNL",
    "last_tracking_event": "out_for_delivery",
    "customer_tier": "Gold",
    "previous_delivery_issues": 0
  },
  "resolution": {
    "id": "RES-DNR-01",
    "name": "Wait and track",
    "message_to_customer": "Your package shows as 'out for delivery' as of yesterday. PostNL sometimes takes 1-2 extra business days. Let's wait until {expected_date_plus_5} — if it still hasn't arrived by then, we'll send a replacement immediately at no cost.",
    "actions_if_unresolved": [
      {
        "description": "Reship if still not delivered after 5 days",
        "command": "gss coolblue.nl shipping report-issue --order-id ORD-12345 --issue not_received",
        "auto_trigger_at": "2026-03-30T00:00:00Z"
      }
    ],
    "actions_immediate": [],
    "follow_up": {
      "check_again_in_days": 5,
      "escalate_if_unresolved": true
    }
  },
  "alternative_resolutions": [
    {
      "id": "RES-DNR-02",
      "name": "Immediate reshipment",
      "condition": "Customer insists or has had previous delivery issues",
      "message_to_customer": "I understand this is frustrating. I'll arrange a replacement shipment right away.",
      "actions_immediate": [
        {
          "description": "Create reshipment",
          "command": "gss coolblue.nl orders reorder --id ORD-12345",
          "requires_confirmation": true
        }
      ]
    },
    {
      "id": "RES-DNR-03",
      "name": "Full refund",
      "condition": "Customer prefers refund over reshipment",
      "message_to_customer": "I'll process a full refund of €79.99 to your original payment method.",
      "actions_immediate": [
        {
          "description": "Process refund",
          "command": "gss coolblue.nl returns initiate --order-id ORD-12345 --item-id ITEM-001 --reason not_received --option return_for_refund",
          "requires_confirmation": true
        }
      ]
    }
  ]
}
```

### 4.3 Protocol Example: "Where's My Refund?"

The most common support question during a return. The customer has shipped the item back and wants to know when their money arrives.

```bash
$ gss coolblue.nl protocols get \
    --trigger "refund-not-received" \
    --context '{"return_id": "RET-789"}'
```

The shop enriches the context by looking up the actual return status:

**Scenario A: Still within inspection SLA (warehouse hasn't finished)**

```json
{
  "context_received": {"return_id": "RET-789"},
  "context_enriched": {
    "return_status": "inspecting",
    "return_received_at": "2026-01-21",
    "days_since_received": 5,
    "inspection_sla_days": 14,
    "days_remaining_in_sla": 9,
    "refund_status": "awaiting_inspection",
    "refund_amount": 79.99
  },
  "resolution": {
    "id": "RES-REFUND-WAIT",
    "name": "Within processing window",
    "message_to_customer": "Your return was received on January 21st and is currently being inspected. Processing takes up to 14 business days — you have 9 days remaining in that window. Once approved, the refund of €79.99 will be sent to your original payment method within 3-5 business days.",
    "actions_immediate": [],
    "follow_up": {
      "check_again_in_days": 9,
      "escalate_if_unresolved": true
    }
  }
}
```

No actions — just a clear status with real dates. The customer knows exactly where they stand.

**Scenario B: Inspection approved, refund is processing**

```json
{
  "context_enriched": {
    "return_status": "approved",
    "refund_status": "processing",
    "refund_amount": 79.99,
    "refund_method": "iDEAL",
    "approved_at": "2026-01-28",
    "estimated_refund_completion": "2026-02-02",
    "days_until_estimated": 3
  },
  "resolution": {
    "id": "RES-REFUND-PROCESSING",
    "name": "Refund in progress",
    "message_to_customer": "Great news — your return was approved on January 28th. The refund of €79.99 is being processed to your iDEAL account and should arrive by February 2nd (3 days from now).",
    "actions_immediate": [],
    "follow_up": {
      "check_again_in_days": 3,
      "escalate_if_unresolved": true
    }
  }
}
```

**Scenario C: SLA exceeded — refund should have been processed by now**

```json
{
  "context_enriched": {
    "return_status": "inspecting",
    "return_received_at": "2026-01-10",
    "days_since_received": 21,
    "inspection_sla_days": 14,
    "days_past_sla": 7,
    "refund_status": "awaiting_inspection"
  },
  "resolution": {
    "id": "RES-REFUND-OVERDUE",
    "name": "Processing overdue — escalate",
    "message_to_customer": "I apologize — your return was received 21 days ago and should have been processed within 14 days. I'm escalating this to our warehouse team for immediate attention. You can expect an update within 24 hours.",
    "actions_immediate": [
      {
        "description": "Escalate to warehouse team",
        "command": "gss coolblue.nl shipping report-issue --order-id ORD-12345 --issue return_processing_delayed",
        "requires_confirmation": false
      }
    ],
    "follow_up": {
      "check_again_in_days": 1,
      "escalate_if_unresolved": true
    }
  },
  "alternative_resolutions": [
    {
      "id": "RES-REFUND-IMMEDIATE",
      "name": "Immediate refund",
      "condition": "Customer insists or SLA exceeded by more than 7 days",
      "message_to_customer": "I understand this has taken too long. I'll process the refund of €79.99 immediately without waiting for the warehouse inspection.",
      "actions_immediate": [
        {
          "description": "Force-process refund",
          "command": "gss coolblue.nl refunds force --return-id RET-789",
          "requires_confirmation": true
        }
      ]
    }
  ]
}
```

This shows the full power of protocols: the same trigger (`refund-not-received`) produces different resolutions based on where the return actually is in the pipeline. The shop defines the rules, the consumer follows them.

### 4.4 What the Consumer Does With This

The consumer (AI agent, app, or device) receives the protocol and:

1. **Presents the primary resolution** to the customer (using `message_to_customer`).
2. **If the customer accepts:** executes `actions_immediate` (with confirmation if flagged).
3. **If the customer pushes back:** moves to `alternative_resolutions` and presents options.
4. **If auto-triggers are set:** schedules the follow-up action.

The consumer NEVER invents a resolution. It follows the shop's protocol. This is what makes GSS reliable — the shop controls the policy, the consumer controls the experience.

### 4.5 Standard Triggers

Every shop that implements protocols MUST support these triggers at minimum:

**Order issues:**

| Trigger                       | Context Fields                                              |
|-------------------------------|-------------------------------------------------------------|
| `order-cancel-request`        | `order_id`, `reason`                                        |
| `order-modification-request`  | `order_id`, `changes` (json)                                |
| `order-status-inquiry`        | `order_id`                                                  |

**Delivery issues:**

| Trigger                       | Context Fields                                              |
|-------------------------------|-------------------------------------------------------------|
| `delivery-not-received`       | `order_id`, `days_since_expected`                           |
| `delivery-damaged`            | `order_id`, `item_id`, `damage_description`                 |
| `delivery-wrong-item`         | `order_id`, `item_id`, `received_item_description`          |
| `delivery-partial`            | `order_id`, `missing_item_ids`                              |

**Return & refund issues:**

| Trigger                       | Context Fields                                              |
|-------------------------------|-------------------------------------------------------------|
| `return-request`              | `order_id`, `item_id`, `reason`                             |
| `return-window-expired`       | `order_id`, `item_id`, `days_past_window`                   |
| `refund-not-received`         | `return_id`, `days_since_approved`                          |
| `refund-wrong-amount`         | `order_id`, `expected_amount`, `received_amount`            |

**Product issues:**

| Trigger                       | Context Fields                                              |
|-------------------------------|-------------------------------------------------------------|
| `product-defective`           | `order_id`, `item_id`, `issue_description`                  |
| `product-not-as-described`    | `order_id`, `item_id`, `discrepancy_description`            |
| `warranty-claim`              | `order_id`, `item_id`, `issue_description`, `purchase_date` |

**Payment issues:**

| Trigger                       | Context Fields                                              |
|-------------------------------|-------------------------------------------------------------|
| `payment-failed`              | `order_id`                                                  |
| `payment-dispute`             | `order_id`, `reason`                                        |
| `double-charged`              | `order_id`, `charge_ids`                                    |
| `invoice-request`             | `order_id`                                                  |

**Subscription issues:**

| Trigger                       | Context Fields                                              |
|-------------------------------|-------------------------------------------------------------|
| `subscription-cancel-request` | `subscription_id`, `reason`                                 |
| `subscription-pause-request`  | `subscription_id`, `duration`                               |
| `subscription-billing-issue`  | `subscription_id`, `issue_description`                      |

**Account issues:**

| Trigger                       | Context Fields                                              |
|-------------------------------|-------------------------------------------------------------|
| `account-access-issue`        | `issue_type` (forgot_password, locked, etc.)                |
| `account-email-change-request`| (none — protocol returns guidance including both standard and recovery flows) |
| `account-data-request`        | `request_type` (export, delete)                             |

### 4.6 Protocol Definition (Shop Side)

Shops define protocols as JSON/YAML rules. Here's how Coolblue might define their `delivery-not-received` protocol:

```yaml
trigger: delivery-not-received
version: 2
rules:
  - condition: "days_since_expected < 2"
    resolution:
      name: "Too early to act"
      message: "Your package is still within the expected delivery window. Delivery is expected by {estimated_delivery}."
      actions: []

  - condition: "days_since_expected >= 2 AND days_since_expected <= 5 AND last_tracking_event != 'delivered'"
    resolution:
      name: "Wait and track"
      message: "Your package shows as '{last_tracking_event}'. {carrier} sometimes takes 1-2 extra business days. Let's wait until {expected_plus_5}."
      follow_up:
        check_again_in_days: 3
        escalate_if_unresolved: true

  - condition: "days_since_expected > 5 OR customer_tier == 'Platinum'"
    resolution:
      name: "Immediate resolution"
      message: "I'm sorry about the delay. I can offer you a replacement or a full refund."
      alternatives:
        - name: "Reship"
          command: "orders reorder --id {order_id}"
          requires_confirmation: true
        - name: "Refund"
          command: "returns initiate --order-id {order_id} --item-id {item_id} --reason not_received"
          requires_confirmation: true

  - condition: "last_tracking_event == 'delivered'"
    resolution:
      name: "Marked as delivered"
      message: "The carrier shows this as delivered on {delivered_at}. Could you check with neighbors or look for a safe-drop notice?"
      follow_up:
        check_again_in_days: 2
      alternatives:
        - name: "Still not found"
          condition: "customer confirms not received after 2 days"
          command: "shipping report-issue --order-id {order_id} --issue not_received"
```

The shop writes these rules. The GSS framework evaluates them against the context. The consumer receives the matched resolution.

---

## 5. Endpoint Resolution

How does `gss coolblue.nl` know where to send requests?

### 5.1 Discovery Methods (in priority order)

**Method 1: `.well-known/gss.json`**

The shop hosts a file at `https://coolblue.nl/.well-known/gss.json`:

```json
{
  "gss_version": "1.0",
  "endpoint": "https://gss.coolblue.nl/v1",
  "docs": "https://gss.coolblue.nl/docs"
}
```

**Method 2: DNS TXT record**

```
_gss.coolblue.nl. IN TXT "v=gss1; endpoint=https://gss.coolblue.nl/v1"
```

**Method 3: Central registry** (for smaller shops that can't manage DNS/well-known)

A public GSS registry (like a DNS for support) that maps shop domains to endpoints:

```bash
$ gss registry lookup coolblue.nl
→ https://gss.coolblue.nl/v1
```

Registry implementers should follow the security model in `docs/registry-security.md`, including mandatory domain-ownership verification and conflict handling.

### 5.2 Transport

GSS is transport-agnostic. The standard defines the command structure and response format. The transport can be:

- **CLI** (for developers and AI agents): `gss coolblue.nl orders get --id ORD-12345`
- **HTTP** (for apps and devices): `POST https://gss.coolblue.nl/v1/orders/get {"id": "ORD-12345"}`
- **WebSocket** (for real-time apps): same JSON payloads over persistent connection

The CLI is a convenience wrapper around the HTTP transport.

---

## 6. Standard Response Envelope

Every GSS response follows the same envelope:

**Success:**

```json
{
  "gss_version": "1.0",
  "status": "ok",
  "data": { ... },
  "meta": {
    "request_id": "req-abc-123",
    "timestamp": "2026-03-28T10:30:00Z",
    "rate_limit": {"remaining": 98, "reset_at": "2026-03-28T11:00:00Z"}
  }
}
```

**Error:**

```json
{
  "gss_version": "1.0",
  "status": "error",
  "error": {
    "code": "ORDER_NOT_FOUND",
    "message": "No order found with ID ORD-99999",
    "domain": "orders",
    "action": "get"
  },
  "meta": { ... }
}
```

**Standard error codes:**

| Code                     | Meaning                                         |
|--------------------------|--------------------------------------------------|
| `NOT_FOUND`              | Resource doesn't exist                           |
| `NOT_AUTHORIZED`         | Auth token missing or invalid                    |
| `FORBIDDEN`              | Authenticated but not allowed (not your order)   |
| `DOMAIN_NOT_SUPPORTED`   | Shop doesn't implement this domain               |
| `ACTION_NOT_SUPPORTED`   | Shop doesn't implement this action               |
| `VALIDATION_ERROR`       | Invalid parameters                               |
| `USE_CHANGE_EMAIL_FLOW`  | Email cannot be changed via this command          |
| `RATE_LIMITED`           | Too many requests                                |
| `CONSUMER_TYPE_BLOCKED`  | This action is blocked for your consumer type    |
| `SERVICE_UNAVAILABLE`    | Shop's systems are down                          |
| `PROTOCOL_NOT_FOUND`     | No protocol defined for this trigger             |

---

## 7. Implementation Guide for Shops

### 7.1 For Shopify Shops

An open-source `gss-provider-shopify` package maps GSS commands to Shopify's Admin API:

```bash
$ pip install gss-provider-shopify
$ gss-provider-shopify init --shop mystore.myshopify.com --api-key shpka_xxx
$ gss-provider-shopify serve --port 8080
```

The provider translates:
- `gss mystore.com orders get --id 5001` → Shopify REST API `GET /admin/api/orders/5001.json`
- `gss mystore.com returns initiate ...` → Shopify returns + refunds API calls
- `gss mystore.com shipping track ...` → Shopify fulfillments API + carrier tracking

Shops customize by adding protocol YAML files:

```
my-gss-config/
├── protocols/
│   ├── delivery-not-received.yaml
│   ├── return-request.yaml
│   └── order-cancel-request.yaml
└── config.yaml
```

### 7.2 For WooCommerce Shops

```bash
$ pip install gss-provider-woocommerce
$ gss-provider-woocommerce init --url https://myshop.com --key ck_xxx --secret cs_xxx
```

### 7.3 For Custom Shops

Implement the GSS provider interface:

```python
from gss_core import GSSProvider, Domain

class MyShopProvider(GSSProvider):
    shop_name = "myshop.com"
    domains = [Domain.ORDERS, Domain.RETURNS, Domain.SHIPPING]

    async def orders_get(self, order_id: str) -> dict:
        # Your logic — call your internal DB, API, whatever
        order = await self.db.get_order(order_id)
        return {
            "id": order.id,
            "status": map_to_gss_status(order.status),
            "items": [...],
            ...
        }

    async def returns_check_eligibility(self, order_id: str, item_id: str) -> dict:
        # Your return policy logic
        ...

    async def protocols_get(self, trigger: str, context: dict) -> dict:
        # Load your protocol YAML, evaluate rules against context
        ...
```

### 7.4 Compliance Levels

Shops can be certified at three levels:

| Level    | Requirements                                                             | Badge          |
|----------|--------------------------------------------------------------------------|----------------|
| **Basic**    | Implements `describe` + `orders` + `shipping` domains                | GSS Basic      |
| **Standard** | Basic + `returns` + `payments` + `account` + at least 5 protocols    | GSS Standard   |
| **Complete** | All 8 domains + full protocol coverage for all standard triggers     | GSS Complete   |

---

## 8. Security Model

Making support machine-readable also makes it machine-exploitable. This section treats security as a first-class part of the standard — not an afterthought.

### 8.1 Threat Model

These are the real attacks GSS must defend against:

**Threat 1: Automated refund fraud at scale**

If `returns initiate` is a single CLI command, a bad actor could script thousands of fraudulent return requests across shops. The standardized interface makes this easier, not harder.

*Mitigation:*
- **Action classification.** GSS defines three action levels:

| Level      | Examples                                          | Requirement                              |
|------------|---------------------------------------------------|------------------------------------------|
| `read`     | orders get, shipping track, account get           | Auth token only                          |
| `request`  | returns initiate, order cancel, subscription cancel | Auth token + confirmation token (2-step) |
| `critical` | account delete, payment method change, address change | Auth token + out-of-band verification (email/SMS OTP) |

Every command in the standard has a classification. Shops CANNOT downgrade a command's level (e.g., they can't make `returns initiate` a `read`-level action). They CAN upgrade it (make a `request`-level action require `critical`-level verification).

- **Two-step execution for `request` actions.** `returns initiate` doesn't execute directly — it returns a `confirmation_token` with a summary. The consumer must send a second request with the token to confirm:

```bash
# Step 1: Request
$ gss shop.com returns initiate --order-id ORD-123 --item-id ITEM-001 --reason defective
{
  "status": "pending_confirmation",
  "confirmation_token": "conf-xyz-789",
  "summary": "Return ITEM-001 (Wireless Headphones, €79.99). Refund to original payment method. Ship via PostNL.",
  "expires_at": "2026-03-28T11:00:00Z"
}

# Step 2: Confirm
$ gss shop.com returns confirm --token conf-xyz-789
{
  "status": "ok",
  "data": {"return_id": "RET-789", ...}
}
```

This prevents accidental or automated execution. The consumer must present the summary to the customer and get agreement before confirming.

- **Velocity limits.** The standard defines minimum rate limits that shops MUST enforce:

| Action Type | Limit Per Customer          | Limit Per Consumer (AI/app) |
|-------------|-----------------------------|-----------------------------|
| `read`      | 100/minute                  | 1000/minute                 |
| `request`   | 5/hour per domain           | 50/hour per domain          |
| `critical`  | 3/hour                      | 10/hour                     |

Shops can set stricter limits. These are floors.

**Threat 2: An AI agent going rogue**

An AI agent (like Support Squad AI) acting on behalf of a customer could misinterpret a protocol and execute the wrong resolution — approving a refund the customer didn't ask for, or cancelling an order by mistake.

*Mitigation:*
- **`requires_confirmation: true` on all protocol actions.** Every action in a protocol response that modifies state MUST have this flag. The consumer MUST obtain explicit customer consent before confirming.
- **Consumer accountability.** Every request carries `GSS-Consumer-Id` and `GSS-Consumer-Type`. If an AI agent misbehaves, the shop can block that consumer specifically without blocking the customer.
- **Protocol responses include the exact message to show the customer.** The AI doesn't compose the message — it relays the shop's `message_to_customer`. This prevents the AI from promising something the shop didn't authorize.
- **Shops can require human-in-the-loop for AI consumers.** A shop can set a policy:

```yaml
consumer_policies:
  ai_agent:
    max_action_level: "request"  # AI can't do "critical" actions
    require_customer_otp_for: ["returns initiate", "order cancel"]
    block_actions: ["account delete", "payment-methods delete"]
    # Note: account change-email is blocked at standard level — not shop-configurable
```

**Threat 3: Token theft / session hijacking**

If a customer's GSS auth token is stolen (from a compromised AI agent, a browser extension, etc.), the attacker has full access to their account operations.

*Mitigation:*
- **Short-lived tokens.** OAuth2 access tokens MUST expire within 1 hour. Refresh tokens MUST be rotatable (one-time use).
- **Scoped tokens.** Consumers request only the scopes they need:

```
gss shop.com auth login --scopes "orders:read,returns:request,shipping:read"
```

A token scoped to `orders:read` cannot initiate a return. An AI agent that only needs to check order status shouldn't have a token that can cancel orders.

- **Token binding.** Tokens are bound to the consumer ID. A token issued to `support-squad-ai` cannot be used by `random-browser-extension`. The shop validates both the customer identity AND the consumer identity on every request.
- **Action-level audit trail.** Every `request` and `critical` action is logged with: customer ID, consumer ID, consumer IP, timestamp, action, parameters, and result. This is not optional — it's required by the standard.

**Threat 4: A malicious shop provider**

A shop implements GSS but does something malicious — logging customer auth tokens, returning fake data, or using the protocol to phish customers.

*Mitigation:*
- **GSS certification.** Shops that want the GSS badge must pass an automated compliance test that checks: proper token handling, correct response formats, rate limiting, audit logging, and privacy compliance.
- **Consumer warnings.** The CLI and HTTP clients warn users when connecting to an uncertified shop:
  ```
  ⚠ shop.com is not GSS certified. Proceed with caution.
  ```
- **Token isolation.** Auth tokens are issued by the shop's OAuth2 server, not by GSS centrally. A malicious shop can only compromise tokens it issued — it can't access tokens from other shops.

**Threat 5: Enumeration attacks**

An attacker tries to enumerate order IDs, customer accounts, or product information by iterating through IDs.

*Mitigation:*
- **Auth-scoped responses only.** `orders get --id ORD-123` only works if the authenticated customer owns that order. If they don't, the response is `FORBIDDEN`, not `NOT_FOUND` (prevents existence leaking).
- **Non-sequential IDs.** The standard recommends (but doesn't require) that shops use non-sequential IDs (UUIDs, hashes) for orders, returns, and customers.
- **Rate limiting on `read` actions.** 100/minute per customer is enough for legitimate use, not enough for enumeration.

**Threat 6: Protocol manipulation**

A customer (or their AI) sends manipulated context to a protocol to trigger a more favorable resolution — e.g., claiming `days_since_expected: 30` when the package was shipped yesterday.

*Mitigation:*
- **Server-side context enrichment.** The protocol system MUST verify context claims against the shop's actual data. The `context_received` (what the consumer sent) is logged separately from `context_enriched` (what the shop verified). Resolution rules run against `context_enriched`, not `context_received`.
- In the protocol response example earlier, you can see this pattern:

```json
{
  "context_received": {"order_id": "ORD-12345", "days_since_expected": 3},
  "context_enriched": {"order_value": 79.99, "carrier": "PostNL", "last_tracking_event": "out_for_delivery", ...}
}
```

The shop looked up the actual order data. The consumer's claim of `days_since_expected: 3` was verified against real tracking data. If the consumer lies, the enriched context corrects it.

### 8.2 Authentication Requirements

| Requirement                              | Mandatory | Notes                                        |
|------------------------------------------|-----------|----------------------------------------------|
| OAuth2 or API key support                | Yes       | At least one method                          |
| Access token max lifetime: 1 hour        | Yes       | Refresh tokens must be one-time-use          |
| Token scoping by domain + action level   | Yes       | Consumers request only what they need        |
| Consumer identification (GSS-Consumer-Id)| Yes       | Every request, logged                        |
| Out-of-band verification for `critical`  | Yes       | Email or SMS OTP                             |
| Two-step confirmation for `request`      | Yes       | confirmation_token pattern                   |
| Token binding to consumer                | Recommended | Prevents token reuse across consumers      |
| IP allowlisting for API key auth         | Recommended | For server-to-server integrations           |

### 8.3 Required Headers on Every Request

```
Authorization: Bearer <customer_token>
GSS-Consumer-Id: support-squad-ai
GSS-Consumer-Type: ai_agent | app | browser_extension | device
GSS-Version: 1.0
GSS-Request-Id: <uuid>
```

### 8.4 Audit Trail Requirements

Every GSS provider MUST log the following for `request` and `critical` actions:

```json
{
  "timestamp": "2026-03-28T10:30:00Z",
  "customer_id": "CUST-456",
  "consumer_id": "support-squad-ai",
  "consumer_type": "ai_agent",
  "consumer_ip": "1.2.3.4",
  "action": "returns initiate",
  "action_level": "request",
  "parameters": {"order_id": "ORD-12345", "item_id": "ITEM-001", "reason": "defective"},
  "confirmation_token": "conf-xyz-789",
  "result": "ok",
  "protocol_used": "return-request v2, rule 3"
}
```

Audit logs MUST be retained for at least 2 years. Customers can request their audit log via `gss <shop> account audit-log`.

### 8.5 Privacy Requirements (GDPR Compliance)

| Requirement                                | Standard Command                    |
|--------------------------------------------|-------------------------------------|
| Right to access personal data              | `gss <shop> account export-data`    |
| Right to deletion                          | `gss <shop> account delete-request` |
| Right to know who accessed data            | `gss <shop> account audit-log`      |
| Data minimization in responses             | Return only fields relevant to the request |
| No bulk data export through GSS            | List commands have mandatory `limit` caps |

### 8.6 Consumer Policies (Shop-Defined + Standard-Enforced)

Some restrictions are **standard-enforced** (shops cannot override them). Others are **shop-defined** (shops configure per their policies).

**Standard-enforced restrictions (cannot be overridden):**

| Restriction                                  | Consumer Types Affected | Reason                                      |
|----------------------------------------------|------------------------|----------------------------------------------|
| `account change-email` blocked               | `ai_agent`             | Email change requires customer to directly receive and enter OTP codes at both addresses. An AI agent cannot do this on behalf of the customer. |
| `account change-email-verify` blocked        | `ai_agent`             | Same — the customer must enter the codes themselves. |
| `account change-email-recover` blocked       | `ai_agent`             | Recovery flow requires phone OTP + identity questions — must be customer-driven. |
| `account change-email-recover-verify` blocked| `ai_agent`             | Same — all verification steps must be done by the customer directly. |

These are built into the standard, not configurable. An AI agent calling `account change-email` MUST receive a `CONSUMER_TYPE_BLOCKED` error regardless of what the shop's consumer policies say.

**Shop-defined restrictions (configurable per shop):**

```yaml
# shop-config/consumer-policies.yaml
consumer_policies:
  ai_agent:
    allowed_action_levels: ["read", "request"]  # No "critical" without human
    max_requests_per_hour: 50
    require_customer_otp_for:
      - "returns initiate"
      - "order cancel"
    blocked_actions:
      - "account delete-request"
      - "account payment-methods delete"
      # Note: account change-email is already blocked at standard level
      # for ai_agent — no need to list it here
    must_use_protocols: true  # AI must follow protocols, can't freestyle

  app:
    allowed_action_levels: ["read", "request", "critical"]
    max_requests_per_hour: 100

  browser_extension:
    allowed_action_levels: ["read"]  # Read-only by default
    max_requests_per_hour: 30
```

This means a shop can say "AI agents can check orders and initiate returns, but they can't delete accounts or change payment methods — and they must always follow our protocols." The consumer policies are returned in the `describe` response so consumers know their limits upfront.

**What should an AI agent do when a customer asks to change their email?**

The AI cannot perform this action, but it can guide the customer:

```
"I can't change your email address directly — for security, you'll need to do this yourself.
You can change it in your account settings at [shop URL].

If you can't access your current email (for example, if there was a typo when you registered),
there's a recovery option that verifies your identity using your phone number instead."
```

The protocol system handles this. A shop defines a protocol for `account-email-change-request` that returns guidance covering both the standard flow and the recovery flow, plus links to the shop's account settings.

---

## 9. Versioning

- The GSS standard is versioned: `1.0`, `1.1`, `2.0`.
- Shops declare their supported version in `describe`.
- Breaking changes (removed fields, changed semantics) require a major version bump.
- New commands and optional fields are minor version bumps.
- Consumers should specify which version they expect: `GSS-Version: 1.0` header.

---

## 10. Roadmap

### Version 1.0 (this document)

- 8 core domains with standard commands
- Resolution protocols
- Discovery (describe, well-known, DNS, registry)
- OAuth2 + API key auth
- CLI + HTTP transport

### Future Versions

- **Real-time notifications:** Shop pushes events to consumer (order shipped, return approved) via webhooks or WebSocket.
- **Multi-language:** `message_to_customer` in protocol responses supports locale parameter.
- **Dispute resolution:** Standardized escalation between shop, customer, and payment provider.
- **Cross-shop operations:** "I bought headphones at Coolblue but the charger at Bol.com" — federated support queries.
- **Certification API:** Automated compliance testing for GSS providers.

---

## 11. Getting Started

### For shops:

```bash
# Install the provider for your platform
pip install gss-provider-shopify

# Initialize with your shop credentials
gss-provider-shopify init --shop mystore.myshopify.com --api-key shpka_xxx

# Write your resolution protocols
mkdir protocols/
# ... create YAML files for your policies ...

# Start serving
gss-provider-shopify serve --port 8080

# Test it
gss mystore.myshopify.com describe
gss mystore.myshopify.com orders list
```

### For consumers (AI agents, apps):

```bash
# Install the CLI
pip install global-support-standard

# Discover a shop
gss coolblue.nl describe

# Authenticate as a customer
gss coolblue.nl auth login --method oauth2

# Start interacting
gss coolblue.nl orders list
gss coolblue.nl protocols get --trigger "delivery-not-received" --context '{"order_id": "ORD-12345", "days_since_expected": 3}'
```

### For Support Squad AI:

Support Squad AI is the first GSS consumer. It uses `gss <shop>` commands as auto-discovered tools, letting the AI agent resolve customer issues by following the shop's own protocols — not by guessing.

---

## 12. Summary

GSS is three things:

1. **A standard command structure** for e-commerce support operations (8 domains, standardized statuses, consistent response format).
2. **A resolution protocol system** that lets shops define their support policies as machine-readable rules, so any consumer can follow them.
3. **A discovery mechanism** that lets any consumer find out what a shop supports and interact with it.

The goal: make human support agents optional for the 80% of support queries that follow a flowchart. Let the customer's device talk directly to the shop's system — instantly, 24/7, in any language, at zero marginal cost.
