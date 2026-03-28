# Getting Started: Consume GSS Shops

## Install

```bash
pip install global-support-standard
```

## Discover

```bash
gss coolblue.nl describe
```

## Authenticate (Agent-first flow)

```bash
gss coolblue.nl auth verify-customer --order-id ORD-12345 --email customer@example.com
gss coolblue.nl auth issue-token --verification-id <verification_id> --method api_key
```

If the customer does not know the order id, use recovery verification (when supported by the shop):

```bash
gss coolblue.nl auth verify-customer --phone +31612345678
gss coolblue.nl auth issue-token --verification-id <verification_id> --method api_key
```

## Interact

```bash
gss coolblue.nl orders list
gss coolblue.nl orders get --id ORD-12345
gss coolblue.nl shipping track --order-id ORD-12345
gss coolblue.nl returns initiate --order-id ORD-12345 --item-id ITEM-001 --reason wrong_size
gss coolblue.nl returns confirm --token conf-xyz-789   # After customer agrees
gss coolblue.nl protocols get --trigger "delivery-not-received" --context '{"order_id": "ORD-12345"}'
```

## For AI Agents

Use `gss --describe` for auto-discovery. Rules: always use protocols, always show confirmation summaries, never attempt critical-level actions, relay protocol messages verbatim.

## Legacy login (dev-only)

`auth login` exists for local/dev compatibility. Production consumers should prefer `verify-customer` -> `issue-token`.
