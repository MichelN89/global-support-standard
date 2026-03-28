# Getting Started: Consume GSS Shops

## Install

```bash
pip install global-support-standard
```

## Discover & Authenticate

```bash
gss coolblue.nl describe
gss coolblue.nl auth login --method oauth2
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
