# Getting Started: Make Your Shop GSS-Compatible

## Step 1: Install

```bash
pip install gss-provider-sdk gss-adapter-shopify   # or gss-adapter-woocommerce
```

## Step 2: Initialize

```bash
gss-init myshop
cd myshop-gss
```

## Step 3: Configure (Shopify example)

```python
from gss_provider import GSSProvider
from gss_adapter_shopify import ShopifyAdapter

provider = GSSProvider(
    shop_name="myshop.com",
    adapter=ShopifyAdapter(shop_url="https://myshop.myshopify.com", api_key="shpka_xxx"),
    protocols_dir="./protocols"
)
provider.serve(port=8080)
```

For custom platforms, implement domain classes. See [Full Spec](../spec/overview.md).

## Step 4: Write Protocols

Customize templates in `protocols/`. See [Protocol Format](../protocols/FORMAT.md).

## Step 5: Validate

```bash
gss validate localhost:8080 --level standard
```

## Step 6: Deploy

```bash
docker build -t myshop-gss . && docker run -p 8080:8080 --env-file .env myshop-gss
```

Make discoverable via `https://myshop.com/.well-known/gss.json` or DNS TXT record.
