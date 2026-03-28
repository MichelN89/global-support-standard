# Global Support Standard (GSS)

**The open protocol for e-commerce customer support.**

GSS lets any webshop expose its support operations through a standardized interface. Any AI agent, app, or device can then provide complete self-service for customers.

```bash
gss coolblue.nl describe
gss coolblue.nl orders get --id ORD-12345
gss coolblue.nl returns check-eligibility --order-id ORD-12345 --item-id ITEM-001
gss coolblue.nl protocols get --trigger "delivery-not-received" --context '{"order_id": "ORD-12345"}'
```

## Quick Start

**For Shops:** `pip install gss-provider-sdk gss-adapter-shopify` — [Getting Started](docs/getting-started-shops.md)

**For Consumers:** `pip install global-support-standard` — [Getting Started](docs/getting-started-consumers.md)

## Core Concepts

**8 Domains:** Orders, Returns, Shipping, Products, Account, Payments, Subscriptions, Loyalty — [Full Spec](spec/overview.md)

**Protocols:** Shop support policies as machine-readable rules — [Format](protocols/FORMAT.md)

**Action Levels:** `read` (view) · `request` (modify, two-step confirmation) · `critical` (OTP required)

**Compliance:** Basic (orders+shipping) · Standard (+returns, payments, 5 protocols) · Complete (all 8 domains)

## How Adapters Work

Shopify, WooCommerce, or custom — adapters translate platform APIs to GSS format:

```python
# Shopify (3 lines)
from gss_provider import GSSProvider
from gss_adapter_shopify import ShopifyAdapter
provider = GSSProvider(shop_name="myshop.com", adapter=ShopifyAdapter(shop_url="...", api_key="..."))

# Custom (implement domain classes)
class MyOrders(OrdersDomain):
    async def get(self, order_id): ...
```

## Repository Structure

```
spec/          The standard (domains, security, discovery)
protocols/     Protocol format + templates + examples
schemas/       JSON Schema for all GSS types
sdk/           Provider SDK (Python)
cli/           Consumer CLI
validator/     Compliance validator
adapters/      Shopify, WooCommerce, ...
docs/          Getting started guides
```

## Packages

| Package | Purpose |
|---------|---------|
| `global-support-standard` | Consumer CLI |
| `gss-provider-sdk` | Build your GSS endpoint |
| `gss-validator` | Validate compliance |
| `gss-adapter-shopify` | Shopify adapter |
| `gss-adapter-woocommerce` | WooCommerce adapter |

## Roadmap

- [x] Specification, Protocol system, Security model, Protocol file format
- [ ] Provider SDK, Consumer CLI, Validator, Adapters

## License

MIT — [LICENSE](LICENSE) · [CONTRIBUTING](CONTRIBUTING.md)

Created by the team behind [Support Squad AI](https://supportsquad.ai).
