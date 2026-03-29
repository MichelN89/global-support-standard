# Commands Reference

This reference lists all currently implemented GSS CLI commands and their syntax.

Command pattern:

```bash
gss <shop> <domain> <action> [--flags]
```

Optional for all domain commands:

- `--channel <channel_id>`

## Orders (5)

- `gss <shop> orders get --id <order_id>`
- `gss <shop> orders list [--status <status>] [--since <iso_datetime>] [--limit <n>]`
- `gss <shop> orders cancel --id <order_id> [--reason <reason>]`
- `gss <shop> orders modify --id <order_id> --changes '<json_object>'`
- `gss <shop> orders reorder --id <order_id>`

## Returns & Refunds (9 + 2)

- `gss <shop> returns check-eligibility --order-id <order_id> --item-id <item_id>`
- `gss <shop> returns initiate --order-id <order_id> --item-id <item_id> --reason <reason> [--option <option>]`
- `gss <shop> returns status --return-id <return_id>`
- `gss <shop> returns list [--status <status>] [--since <iso_datetime>]`
- `gss <shop> returns cancel --return-id <return_id>`
- `gss <shop> returns dispute --return-id <return_id> --reason <reason>`
- `gss <shop> returns request-return-back --return-id <return_id>`
- `gss <shop> returns accept-partial --return-id <return_id> --option <option>`
- `gss <shop> returns confirm --token <confirmation_token>`
- `gss <shop> refunds status --refund-id <refund_id>`
- `gss <shop> refunds list [--since <iso_datetime>]`

## Shipping (5)

- `gss <shop> shipping track --order-id <order_id>`
- `gss <shop> shipping report-issue --order-id <order_id> --issue <issue>`
- `gss <shop> shipping change-address --order-id <order_id> --address '<json_or_text>'`
- `gss <shop> shipping request-redelivery --order-id <order_id> [--date <yyyy-mm-dd>]`
- `gss <shop> shipping delivery-preferences --set '<json_or_text>'`

## Products (6)

- `gss <shop> products get --id <product_id>`
- `gss <shop> products search --query <query> [--category <category>] [--limit <n>]`
- `gss <shop> products check-availability --id <product_id> [--postal-code <postal_code>]`
- `gss <shop> products warranty-status --id <product_id> --purchase-date <yyyy-mm-dd>`
- `gss <shop> products notify-restock --id <product_id> --email <email>`
- `gss <shop> products compare --ids <id1,id2,id3>`

## Account (13)

- `gss <shop> account get`
- `gss <shop> account update --changes '<json_object>'`
- `gss <shop> account addresses list`
- `gss <shop> account addresses add --address '<json_object>'`
- `gss <shop> account addresses update --id <address_id> --changes '<json_object>'`
- `gss <shop> account addresses delete --id <address_id>`
- `gss <shop> account change-email --new-email <email>`
- `gss <shop> account change-email-recover --new-email <email>`
- `gss <shop> account payment-methods list`
- `gss <shop> account payment-methods add --method '<json_object>'`
- `gss <shop> account payment-methods delete --id <method_id>`
- `gss <shop> account delete-request`
- `gss <shop> account export-data`
- `gss <shop> account audit-log [--since <iso_datetime>] [--limit <n>]`

## Payments (5)

- `gss <shop> payments get --order-id <order_id>`
- `gss <shop> payments invoice --order-id <order_id>`
- `gss <shop> payments dispute --order-id <order_id> --reason <reason>`
- `gss <shop> payments retry --order-id <order_id>`
- `gss <shop> payments list [--since <iso_datetime>] [--status <status>]`

## Subscriptions (8)

- `gss <shop> subscriptions list`
- `gss <shop> subscriptions get --id <subscription_id>`
- `gss <shop> subscriptions pause --id <subscription_id> [--until <yyyy-mm-dd>]`
- `gss <shop> subscriptions resume --id <subscription_id>`
- `gss <shop> subscriptions cancel --id <subscription_id> [--reason <reason>]`
- `gss <shop> subscriptions modify --id <subscription_id> --changes '<json_object>'`
- `gss <shop> subscriptions skip-next --id <subscription_id>`
- `gss <shop> subscriptions change-frequency --id <subscription_id> --cycle <cycle>`

## Loyalty (6)

- `gss <shop> loyalty balance`
- `gss <shop> loyalty history [--since <iso_datetime>] [--limit <n>]`
- `gss <shop> loyalty redeem --points <points> --order-id <order_id>`
- `gss <shop> loyalty rewards list`
- `gss <shop> loyalty rewards redeem --reward-id <reward_id>`
- `gss <shop> loyalty tier-benefits`

## Protocols (1)

- `gss <shop> protocols get --trigger <trigger> --context '<json_object>'`

## Auth

- `gss <shop> auth agent --key <trusted_agent_key>`
- `gss <shop> auth verify-customer [--order-id <order_id>] [--email <email>] [--phone <phone>] [--channel <channel_id>]`
- `gss <shop> auth issue-token --verification-id <verification_id> [--method <oauth2|api_key>]`
- `gss <shop> auth login --method <oauth2|api_key> [--customer-id <id>]` (deprecated)

## Validation

- `gss validate <shop> [--level <basic|standard|complete>]`
