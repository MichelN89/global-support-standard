# Getting Started: Consume GSS Shops

## Install

```bash
pip install global-support-standard
```

## Discover

```bash
gss coolblue.nl describe
```

If your shop endpoint is hosted on Cloud Run, set the CLI endpoint first:

```bash
export GSS_DEFAULT_ENDPOINT="https://gss-provider-125211190390.europe-west4.run.app/v1"
# optional shop-specific override:
export GSS_SHOP_COOLBLUE_NL_ENDPOINT="https://gss-provider-125211190390.europe-west4.run.app/v1"
```

## Authenticate (Agent-first flow)

```bash
gss coolblue.nl auth agent --key <trusted_agent_key>
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
gss coolblue.nl orders list --channel web
gss coolblue.nl orders get --id ORD-12345 --channel web
gss coolblue.nl shipping track --order-id ORD-12345 --channel web
gss coolblue.nl returns initiate --order-id ORD-12345 --item-id ITEM-001 --reason wrong_size --channel web
gss coolblue.nl returns confirm --token conf-xyz-789   # After customer agrees
gss coolblue.nl protocols get --trigger "delivery-not-received" --context '{"order_id": "ORD-12345"}'
```

## Validate a Shop

```bash
gss validate coolblue.nl --level standard
```

## For AI Agents

Use `gss --describe` for auto-discovery. Rules: always use protocols, always show confirmation summaries, never attempt critical-level actions, relay protocol messages verbatim.

## Legacy login (compatibility only)

`auth login` exists for local/dev compatibility. Production consumers should prefer `verify-customer` -> `issue-token`.
