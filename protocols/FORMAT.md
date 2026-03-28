# GSS Protocol File Format Specification

**Version:** 1.0
**Date:** 2026-03-28

---

## 1. File Format

Protocol files use **Markdown with YAML frontmatter**. All machine-readable data lives in the frontmatter (between `---` markers). The markdown body below the frontmatter is optional human documentation — the parser ignores it.

**File location:** `protocols/<trigger-name>.md`
**Example:** `protocols/delivery-not-received.md`

**Parsing:** Read everything between the first two `---` markers as YAML. That's the full protocol definition.

---

## 2. Complete Template

```markdown
---
# ============================================================
# GSS PROTOCOL DEFINITION
# ============================================================
# This file defines how the shop handles a specific support
# scenario. The GSS system evaluates the rules against the
# context and returns the matching resolution to the consumer.
# ============================================================

# METADATA
# --------------------------------------------------------
trigger: "delivery-not-received"        # Unique trigger ID. Must match a standard GSS trigger or be prefixed with "custom-" for shop-specific triggers.
version: 2                              # Increment when changing rules. Consumers see this in responses.
name: "Delivery Not Received"           # Human-readable name for UI display.
description: "Handles cases where a customer reports they haven't received their package."
domain: "shipping"                      # GSS domain: orders, returns, shipping, products, account, payments, subscriptions, loyalty
active: true                            # Set to false to disable without deleting.
updated_at: "2026-03-28T10:00:00Z"
updated_by: "jan@company.nl"

# CONTEXT REQUIREMENTS
# --------------------------------------------------------
# Fields the consumer SHOULD provide. The shop enriches
# these server-side — consumer-provided values are advisory,
# never trusted for rule evaluation.
context_fields:
  required:
    - name: "order_id"
      type: "string"
      description: "The order ID the customer is asking about"
  optional:
    - name: "days_since_expected"
      type: "integer"
      description: "Days since the expected delivery date"
    - name: "item_id"
      type: "string"
      description: "Specific item ID if only part of the order"

# ENRICHMENT
# --------------------------------------------------------
# Fields the shop adds server-side by looking up actual data.
# These are the fields used in rule conditions — NOT the
# consumer-provided context.
enrichment_fields:
  - name: "order_status"
    source: "orders.status"
    description: "Current order status from the shop's system"
  - name: "carrier"
    source: "shipments.carrier"
  - name: "tracking_status"
    source: "shipments.last_tracking_event"
  - name: "shipped_at"
    source: "shipments.shipped_at"
  - name: "expected_delivery"
    source: "shipments.estimated_delivery"
  - name: "days_since_expected"
    source: "calculated"
    description: "Calculated from expected_delivery vs today. Overrides consumer-provided value."
  - name: "order_value"
    source: "orders.total"
  - name: "customer_tier"
    source: "customers.loyalty_tier"
  - name: "previous_delivery_issues"
    source: "customers.delivery_issue_count_12m"
    description: "Number of delivery issues in the past 12 months"

# RULES
# --------------------------------------------------------
# Evaluated top-to-bottom. First matching rule wins.
# Conditions use enriched fields (NOT consumer-provided).
# Use simple comparison syntax:
#   field == "value"          exact match
#   field != "value"          not equal
#   field > 5                 greater than
#   field >= 5                greater than or equal
#   field < 5                 less than
#   field <= 5                less than or equal
#   field in ["a", "b"]      one of
#   field not_in ["a", "b"]  not one of
#   Combine with AND / OR (AND binds tighter)
#
rules:

  # ---- Rule 1: Not shipped yet ----
  - id: "not-shipped"
    condition: 'order_status in ["pending", "confirmed", "processing"]'
    resolution:
      name: "Not shipped yet"
      message_to_customer: >
        Your order hasn't shipped yet — it's currently being processed.
        Expected shipping date is {expected_shipping_date}.
        I'll keep an eye on it for you.
      actions: []
      follow_up:
        check_again_in_days: 1
        escalate_if_unresolved: false

  # ---- Rule 2: Shipped, within delivery window ----
  - id: "in-transit-on-time"
    condition: 'order_status == "shipped" AND days_since_expected < 0'
    resolution:
      name: "In transit, on schedule"
      message_to_customer: >
        Your package is on its way with {carrier}! It's expected to arrive
        by {expected_delivery}. You can track it here: {tracking_url}
      actions: []
      follow_up: null

  # ---- Rule 3: Carrier says delivered, customer says not received ----
  - id: "marked-delivered"
    condition: 'tracking_status == "delivered"'
    resolution:
      name: "Marked as delivered"
      message_to_customer: >
        The carrier shows your package as delivered on {delivered_at}.
        Could you check with neighbors or look for a delivery notice?
        Sometimes packages are left in a safe spot.
      actions: []
      follow_up:
        check_again_in_days: 2
        escalate_if_unresolved: true
    alternatives:
      - id: "marked-delivered-still-missing"
        name: "Customer confirms not received"
        condition_hint: "Customer has checked and still can't find it"
        resolution:
          message_to_customer: >
            I'm sorry to hear that. I'll open an investigation with {carrier}
            and arrange a replacement shipment for you right away.
          actions:
            - description: "Open carrier investigation"
              command: "shipping report-issue --order-id {order_id} --issue not_received"
              requires_confirmation: false
            - description: "Send replacement"
              command: "orders reorder --id {order_id}"
              requires_confirmation: true

  # ---- Rule 4: Late delivery, 1-5 days overdue ----
  - id: "slightly-late"
    condition: 'days_since_expected >= 1 AND days_since_expected <= 5 AND tracking_status != "delivered"'
    resolution:
      name: "Wait and track"
      message_to_customer: >
        Your package is running a bit late — it was expected by {expected_delivery}.
        {carrier} sometimes takes 1-2 extra business days. Let's wait until
        {expected_plus_5} — if it still hasn't arrived, I'll arrange a solution
        right away.
      actions: []
      follow_up:
        check_again_in_days: 3
        escalate_if_unresolved: true
    alternatives:
      - id: "slightly-late-priority"
        name: "Immediate reshipment"
        condition_hint: "Customer insists or has had previous delivery issues"
        show_if: 'previous_delivery_issues > 0 OR customer_tier in ["Gold", "Platinum"]'
        resolution:
          message_to_customer: >
            I understand this is frustrating, especially since you've had
            delivery issues before. I'll arrange a replacement right away.
          actions:
            - description: "Send replacement"
              command: "orders reorder --id {order_id}"
              requires_confirmation: true

  # ---- Rule 5: Very late delivery, 5+ days overdue ----
  - id: "very-late"
    condition: 'days_since_expected > 5 AND tracking_status != "delivered"'
    resolution:
      name: "Overdue — immediate resolution"
      message_to_customer: >
        I apologize — your package is significantly delayed. I can offer
        you a replacement shipment or a full refund. Which would you prefer?
      actions: []
    alternatives:
      - id: "very-late-reship"
        name: "Replacement shipment"
        condition_hint: "Customer wants the product"
        resolution:
          message_to_customer: >
            I'll send a replacement right away. You should receive it within
            {standard_delivery_days} business days.
          actions:
            - description: "Send replacement"
              command: "orders reorder --id {order_id}"
              requires_confirmation: true
      - id: "very-late-refund"
        name: "Full refund"
        condition_hint: "Customer prefers money back"
        resolution:
          message_to_customer: >
            I'll process a full refund of {order_total} to your original
            payment method. You should see it within 3-5 business days.
          actions:
            - description: "Process refund"
              command: "returns initiate --order-id {order_id} --item-id all --reason not_received --option return_for_refund"
              requires_confirmation: true

  # ---- Rule 6: Platinum customers — always offer immediate resolution ----
  - id: "platinum-override"
    condition: 'customer_tier == "Platinum" AND days_since_expected >= 1'
    priority: 1    # Higher priority — evaluated before other rules with same match
    resolution:
      name: "Platinum priority handling"
      message_to_customer: >
        I'm sorry about the delay on your order. As a Platinum member,
        I can arrange an immediate replacement or refund — whichever you prefer.
      actions: []
    alternatives:
      - id: "platinum-reship"
        name: "Priority replacement"
        resolution:
          message_to_customer: "I'll send a priority replacement right away."
          actions:
            - description: "Priority reshipment"
              command: "orders reorder --id {order_id} --priority express"
              requires_confirmation: true
      - id: "platinum-refund"
        name: "Immediate refund"
        resolution:
          message_to_customer: "I'll process your refund immediately."
          actions:
            - description: "Immediate refund"
              command: "returns initiate --order-id {order_id} --item-id all --reason not_received --option return_for_refund"
              requires_confirmation: true

# FALLBACK
# --------------------------------------------------------
# If no rule matches, this resolution is returned.
# This should ALWAYS escalate to a human.
fallback:
  resolution:
    name: "No matching rule — escalate"
    message_to_customer: >
      I'm looking into this for you. Let me connect you with our
      support team who can help resolve this right away.
    actions:
      - description: "Escalate to human support"
        command: "chatwoot escalate --conversation-id {conversation_id}"
        requires_confirmation: false
    follow_up: null

---

# Delivery Not Received Protocol

## Overview

This protocol handles cases where a customer reports they haven't received their order. It covers scenarios from "not shipped yet" through "very late delivery" with appropriate resolutions at each stage.

## Rule Summary

| Rule | Condition | Resolution |
|------|-----------|------------|
| Not shipped | Order still processing | Tell customer when it will ship |
| In transit | Before expected date | Share tracking link |
| Marked delivered | Carrier says delivered | Ask customer to check around |
| Slightly late (1-5 days) | Overdue but within tolerance | Wait and track, with escalation option |
| Very late (5+ days) | Significantly overdue | Offer replacement or refund |
| Platinum override | Premium customer, any delay | Immediate resolution options |

## Change Log

- v2 (2026-03-28): Added Platinum override rule. Adjusted slightly-late threshold from 3 to 5 days.
- v1 (2026-03-01): Initial protocol.
```

---

## 3. Field Reference

### Metadata Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `trigger` | string | Yes | Must match a standard GSS trigger (e.g., `delivery-not-received`) or use `custom-` prefix. |
| `version` | integer | Yes | Increment on changes. Returned in protocol responses. |
| `name` | string | Yes | Human-readable name for UI display. |
| `description` | string | Yes | What this protocol handles. |
| `domain` | string | Yes | GSS domain: `orders`, `returns`, `shipping`, `products`, `account`, `payments`, `subscriptions`, `loyalty`. |
| `active` | boolean | Yes | `false` disables the protocol without deleting it. |
| `updated_at` | ISO 8601 | Yes | Last modification timestamp. |
| `updated_by` | string | No | Email of person/system that last modified. |

### Context Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `context_fields.required[]` | list | Yes | Fields the consumer MUST provide. Request is rejected without them. |
| `context_fields.optional[]` | list | No | Fields the consumer MAY provide for better results. |
| `.name` | string | Yes | Field name. |
| `.type` | string | Yes | `string`, `integer`, `number`, `boolean`, `date`. |
| `.description` | string | No | Human-readable description. |

### Enrichment Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enrichment_fields[]` | list | Yes | Fields the shop adds server-side. These are the REAL values used in conditions. |
| `.name` | string | Yes | Field name used in rule conditions. |
| `.source` | string | Yes | Where the value comes from: `table.column` or `calculated`. |
| `.description` | string | No | How it's derived (especially for calculated fields). |

### Rules

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `rules[]` | list | Yes | Ordered list. First match wins (unless `priority` overrides). |
| `.id` | string | Yes | Unique within this protocol. Logged in audit trail. |
| `.condition` | string | Yes | Expression using enriched fields. See condition syntax below. |
| `.priority` | integer | No | Default 0. Higher priority rules are evaluated first, regardless of position. |
| `.resolution` | object | Yes | What to do when this rule matches. |
| `.alternatives[]` | list | No | Additional options the consumer can offer if the customer pushes back. |

### Resolution Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `.name` | string | Yes | Short name for logging and UI. |
| `.message_to_customer` | string | Yes | Exact text the consumer should relay. Supports `{field}` template variables from enriched context. |
| `.actions[]` | list | Yes | GSS commands to execute. Empty list `[]` means no actions (information only). |
| `.follow_up` | object | No | Schedule a check-back. `null` means no follow-up. |

### Action Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `.description` | string | Yes | Human-readable description of what this action does. |
| `.command` | string | Yes | GSS command to execute. Supports `{field}` template variables. |
| `.requires_confirmation` | boolean | Yes | If `true`, the consumer MUST show the action summary and get customer agreement before executing. Always `true` for `request`-level actions. |

### Follow-Up Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `.check_again_in_days` | integer | Yes | Days until the consumer should re-check this protocol. |
| `.escalate_if_unresolved` | boolean | Yes | If still unresolved after follow-up, escalate to human. |

### Alternative Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `.id` | string | Yes | Unique within this rule. |
| `.name` | string | Yes | Short name. Shown as an option to the customer. |
| `.condition_hint` | string | No | Human-readable hint for when this alternative applies. For the consumer's judgment, not for automated evaluation. |
| `.show_if` | string | No | Condition expression. If provided, this alternative is only shown when the condition is true. If absent, always available as an alternative. |
| `.resolution` | object | Yes | Same structure as the main resolution. |

### Fallback

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fallback` | object | Yes | Every protocol MUST have a fallback. |
| `.resolution` | object | Yes | Returned when no rule matches. Should always escalate to human. |

---

## 4. Condition Syntax

Conditions are simple expressions evaluated against enriched fields.

### Operators

| Operator | Example | Description |
|----------|---------|-------------|
| `==` | `status == "shipped"` | Equals |
| `!=` | `status != "cancelled"` | Not equals |
| `>` | `days > 5` | Greater than |
| `>=` | `days >= 5` | Greater than or equal |
| `<` | `days < 3` | Less than |
| `<=` | `days <= 3` | Less than or equal |
| `in` | `tier in ["Gold", "Platinum"]` | Value is in list |
| `not_in` | `status not_in ["cancelled", "refunded"]` | Value is not in list |

### Combining Conditions

| Combinator | Example | Description |
|------------|---------|-------------|
| `AND` | `status == "shipped" AND days > 5` | Both must be true |
| `OR` | `tier == "Platinum" OR previous_issues > 2` | Either must be true |

`AND` binds tighter than `OR`. Use parentheses for clarity:

```
(tier == "Platinum" OR previous_issues > 2) AND days_since_expected >= 1
```

### Template Variables in Messages and Commands

Use `{field_name}` to insert enriched context values:

```yaml
message_to_customer: "Your package was shipped via {carrier} on {shipped_at}."
command: "orders reorder --id {order_id}"
```

Available variables: all fields from `enrichment_fields` plus all fields from `context_fields.required` and `context_fields.optional`.

---

## 5. Standard Protocol Templates

Every shop implementing GSS protocols SHOULD start with these templates and customize the thresholds, messages, and actions for their policies.

### Required Protocols (for GSS Standard/Complete certification)

| File | Trigger | Domain |
|------|---------|--------|
| `delivery-not-received.md` | `delivery-not-received` | shipping |
| `delivery-damaged.md` | `delivery-damaged` | shipping |
| `delivery-wrong-item.md` | `delivery-wrong-item` | shipping |
| `return-request.md` | `return-request` | returns |
| `return-window-expired.md` | `return-window-expired` | returns |
| `refund-not-received.md` | `refund-not-received` | returns |
| `order-cancel-request.md` | `order-cancel-request` | orders |
| `product-defective.md` | `product-defective` | products |
| `warranty-claim.md` | `warranty-claim` | products |
| `payment-failed.md` | `payment-failed` | payments |

### Optional Protocols

| File | Trigger | Domain |
|------|---------|--------|
| `delivery-partial.md` | `delivery-partial` | shipping |
| `order-modification-request.md` | `order-modification-request` | orders |
| `refund-wrong-amount.md` | `refund-wrong-amount` | returns |
| `double-charged.md` | `double-charged` | payments |
| `subscription-cancel-request.md` | `subscription-cancel-request` | subscriptions |
| `subscription-pause-request.md` | `subscription-pause-request` | subscriptions |
| `account-access-issue.md` | `account-access-issue` | account |
| `account-email-change-request.md` | `account-email-change-request` | account |

---

## 6. Parsing Example (Python)

```python
import yaml

def parse_protocol(filepath: str) -> dict:
    """Parse a GSS protocol .md file. Returns the YAML frontmatter as a dict."""
    with open(filepath) as f:
        content = f.read()

    # Extract YAML frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Invalid protocol file: {filepath} — missing YAML frontmatter")

    protocol = yaml.safe_load(parts[1])

    if not protocol.get("trigger"):
        raise ValueError(f"Protocol missing 'trigger' field: {filepath}")
    if not protocol.get("rules"):
        raise ValueError(f"Protocol missing 'rules' field: {filepath}")
    if not protocol.get("fallback"):
        raise ValueError(f"Protocol missing 'fallback' field: {filepath}")

    return protocol


def evaluate_protocol(protocol: dict, enriched_context: dict) -> dict:
    """
    Evaluate a protocol's rules against enriched context.
    Returns the matching resolution.
    """
    # Sort by priority (higher first), then by position
    rules = sorted(protocol["rules"], key=lambda r: -r.get("priority", 0))

    for rule in rules:
        if not protocol.get("active", True):
            continue
        if evaluate_condition(rule["condition"], enriched_context):
            return {
                "trigger": protocol["trigger"],
                "version": protocol["version"],
                "matched_rule": rule["id"],
                "resolution": render_resolution(rule["resolution"], enriched_context),
                "alternatives": [
                    {
                        "id": alt["id"],
                        "name": alt["name"],
                        "condition_hint": alt.get("condition_hint"),
                        "resolution": render_resolution(alt["resolution"], enriched_context)
                    }
                    for alt in rule.get("alternatives", [])
                    if should_show_alternative(alt, enriched_context)
                ]
            }

    # No rule matched — return fallback
    return {
        "trigger": protocol["trigger"],
        "version": protocol["version"],
        "matched_rule": "fallback",
        "resolution": render_resolution(protocol["fallback"]["resolution"], enriched_context),
        "alternatives": []
    }


def render_resolution(resolution: dict, context: dict) -> dict:
    """Replace {field} template variables in messages and commands."""
    rendered = dict(resolution)
    rendered["message_to_customer"] = resolution["message_to_customer"].format(**context)
    rendered["actions"] = [
        {
            **action,
            "command": action["command"].format(**context)
        }
        for action in resolution.get("actions", [])
    ]
    return rendered
```

---

## 7. UI Schema

For shops that define protocols via a UI instead of editing files directly, the UI should map to this structure:

```
Protocol Editor
├── Metadata Section
│   ├── Trigger (dropdown: standard triggers + "custom-" prefix input)
│   ├── Name (text)
│   ├── Description (text)
│   ├── Domain (dropdown)
│   └── Active (toggle)
│
├── Context Section
│   ├── Required Fields (repeatable: name, type, description)
│   └── Optional Fields (repeatable: name, type, description)
│
├── Enrichment Section
│   └── Enrichment Fields (repeatable: name, source, description)
│
├── Rules Section (sortable list)
│   └── For each rule:
│       ├── ID (auto-generated or custom)
│       ├── Condition (expression builder or raw input)
│       ├── Priority (number, default 0)
│       ├── Resolution
│       │   ├── Name (text)
│       │   ├── Message to Customer (rich text, {variables} highlighted)
│       │   ├── Actions (repeatable: description, command, requires_confirmation)
│       │   └── Follow-up (days + escalate toggle, or "none")
│       └── Alternatives (repeatable)
│           ├── Name (text)
│           ├── Condition Hint (text)
│           ├── Show If (condition expression, optional)
│           └── Resolution (same as above)
│
├── Fallback Section
│   └── Resolution (same structure, always required)
│
└── Documentation Section (optional markdown editor for change log / notes)
```

The UI generates the .md file. The .md file is the source of truth. The UI can also read .md files back for editing.
