---
trigger: "return-request"
version: 1
name: "Return Request"
description: "Handles cases where a customer wants to return an item. Checks eligibility, offers return options, and handles edge cases like expired windows."
domain: "returns"
active: true
updated_at: "2026-03-28T10:00:00Z"
updated_by: "jan@company.nl"

context_fields:
  required:
    - name: "order_id"
      type: "string"
      description: "The order the customer wants to return"
    - name: "item_id"
      type: "string"
      description: "The specific item to return"
    - name: "reason"
      type: "string"
      description: "Customer's stated reason for returning"
  optional:
    - name: "description"
      type: "string"
      description: "Additional details about why they're returning"

enrichment_fields:
  - name: "order_status"
    source: "orders.status"
  - name: "order_date"
    source: "orders.placed_at"
  - name: "item_name"
    source: "order_items.name"
  - name: "item_price"
    source: "order_items.price"
  - name: "item_delivered"
    source: "order_items.delivered"
    description: "Whether this item has been delivered"
  - name: "return_window_days"
    source: "shop_settings.return_window_days"
  - name: "return_window_closes"
    source: "calculated"
    description: "order_date + return_window_days"
  - name: "days_remaining_in_window"
    source: "calculated"
    description: "return_window_closes - today. Negative = expired."
  - name: "is_eligible"
    source: "calculated"
    description: "days_remaining_in_window > 0 AND item_delivered == true AND order_status != 'cancelled'"
  - name: "item_condition_required"
    source: "shop_settings.return_condition"
    description: "e.g., 'original_packaging', 'unused', 'any'"
  - name: "free_return_shipping"
    source: "shop_settings.free_returns"
  - name: "customer_tier"
    source: "customers.loyalty_tier"
  - name: "previous_returns_90d"
    source: "customers.return_count_90d"
    description: "Number of returns in past 90 days"

rules:

  - id: "not-delivered"
    condition: 'item_delivered == false'
    resolution:
      name: "Item not yet delivered"
      message_to_customer: >
        Your item "{item_name}" hasn't been delivered yet, so we can't
        process a return at this time. Would you like to cancel the order
        instead, or wait for delivery first?
      actions: []
      follow_up: null
    alternatives:
      - id: "not-delivered-cancel"
        name: "Cancel the order"
        condition_hint: "Customer doesn't want to wait"
        resolution:
          message_to_customer: >
            I'll cancel {item_name} from your order. The refund of
            {item_price} will be processed within 3-5 business days.
          actions:
            - description: "Cancel item from order"
              command: "orders cancel --id {order_id} --reason customer_request"
              requires_confirmation: true

  - id: "order-cancelled"
    condition: 'order_status == "cancelled"'
    resolution:
      name: "Order already cancelled"
      message_to_customer: >
        This order has already been cancelled. If you're waiting for a
        refund, you can check the status with me anytime.
      actions: []
      follow_up: null

  - id: "eligible-standard"
    condition: 'is_eligible == true AND reason in ["changed_mind", "wrong_size", "wrong_color", "arrived_too_late", "other"]'
    resolution:
      name: "Eligible — standard return"
      message_to_customer: >
        You're within the return window ({days_remaining_in_window} days remaining).
        I can set up a return for "{item_name}" right away.

        You'll receive a shipping label via email. Once we receive and inspect
        the item, your refund of {item_price} will be processed within 14
        business days.

        Please note: the item should be in {item_condition_required} condition.
      actions:
        - description: "Check eligibility and initiate return"
          command: "returns initiate --order-id {order_id} --item-id {item_id} --reason {reason} --option return_for_refund"
          requires_confirmation: true
      follow_up: null

  - id: "eligible-defective"
    condition: 'is_eligible == true AND reason in ["defective", "not_as_described", "wrong_item"]'
    resolution:
      name: "Eligible — defective/wrong item"
      message_to_customer: >
        I'm sorry to hear that. I'll set up a return for "{item_name}"
        right away. Since the item is {reason}, return shipping is free
        and we'll process your refund of {item_price} as soon as we
        receive it — no need to worry about the original packaging.
      actions:
        - description: "Initiate return for defective item"
          command: "returns initiate --order-id {order_id} --item-id {item_id} --reason {reason} --option return_for_refund"
          requires_confirmation: true
      follow_up: null
    alternatives:
      - id: "defective-exchange"
        name: "Exchange instead of refund"
        condition_hint: "Customer wants a replacement"
        resolution:
          message_to_customer: >
            I can send you a replacement instead. I'll set up the return
            and ship the new item right away — you don't need to wait for
            us to receive the old one.
          actions:
            - description: "Initiate exchange"
              command: "returns initiate --order-id {order_id} --item-id {item_id} --reason {reason} --option exchange"
              requires_confirmation: true

  - id: "window-expired-recent"
    condition: 'days_remaining_in_window < 0 AND days_remaining_in_window >= -7'
    resolution:
      name: "Just expired (within 7 days)"
      message_to_customer: >
        The return window for this item closed {days_remaining_in_window} days
        ago (on {return_window_closes}). Unfortunately I can't process a return
        at this time.
      actions: []
      follow_up: null
    alternatives:
      - id: "window-expired-exception"
        name: "Request exception"
        show_if: 'customer_tier in ["Gold", "Platinum"] OR previous_returns_90d == 0'
        condition_hint: "Loyal customer or first-time return"
        resolution:
          message_to_customer: >
            The return window has technically closed, but since you're a
            valued customer, I can make an exception this time. Shall I
            set up the return?
          actions:
            - description: "Initiate return (exception)"
              command: "returns initiate --order-id {order_id} --item-id {item_id} --reason {reason} --option return_for_refund"
              requires_confirmation: true

  - id: "window-expired-long"
    condition: 'days_remaining_in_window < -7'
    resolution:
      name: "Window expired (more than 7 days)"
      message_to_customer: >
        The return window for this item closed on {return_window_closes}
        ({days_remaining_in_window} days ago). Unfortunately we're unable
        to process a return for this item.

        If the item is defective, you may still be covered under the
        manufacturer's warranty.
      actions: []
      follow_up: null
    alternatives:
      - id: "window-expired-warranty"
        name: "Check warranty"
        condition_hint: "Item may be under warranty"
        resolution:
          message_to_customer: >
            Let me check if your item is still under warranty.
          actions:
            - description: "Check warranty eligibility"
              command: "products warranty-status --id {item_id} --purchase-date {order_date}"
              requires_confirmation: false

  - id: "excessive-returns"
    condition: 'previous_returns_90d >= 5'
    priority: 2
    resolution:
      name: "High return frequency — flag for review"
      message_to_customer: >
        I'd be happy to help with your return. Let me connect you with
        our support team who can assist you personally.
      actions:
        - description: "Escalate to human (high return frequency)"
          command: "chatwoot escalate --conversation-id {conversation_id}"
          requires_confirmation: false
      follow_up: null

fallback:
  resolution:
    name: "No matching rule — escalate"
    message_to_customer: >
      I'm looking into your return request. Let me connect you with
      our support team who can help you right away.
    actions:
      - description: "Escalate to human support"
        command: "chatwoot escalate --conversation-id {conversation_id}"
        requires_confirmation: false
    follow_up: null

---

# Return Request Protocol

## Overview

Handles all customer return requests. Checks eligibility (delivery status, return window), differentiates between standard returns and defective/wrong items, and handles expired windows with loyalty-based exceptions.

## Rule Summary

| Rule | Condition | Resolution |
|------|-----------|------------|
| Not delivered | Item hasn't arrived yet | Can't return — offer cancellation |
| Order cancelled | Order already cancelled | Inform customer |
| Eligible (standard) | Within window, normal reason | Initiate return with label |
| Eligible (defective) | Within window, defect/wrong item | Free return shipping, faster processing |
| Window expired (<7 days) | Just expired | Deny, but offer exception for loyal customers |
| Window expired (>7 days) | Long expired | Deny, suggest warranty check |
| Excessive returns | 5+ returns in 90 days | Escalate to human |

## Change Log

- v1 (2026-03-28): Initial protocol.
