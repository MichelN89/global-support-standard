# Deploy to Google Cloud Run

This runbook deploys `gss_provider` to Cloud Run as a public HTTPS endpoint.

## 1) Prerequisites

- Google Cloud project with billing enabled
- Google Cloud CLI installed and authenticated
- Permissions: Cloud Run Admin, Service Account User, Artifact Registry Admin

## 2) Set variables

```bash
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="europe-west4"
export SERVICE_NAME="gss-provider"
export ARTIFACT_REPOSITORY="gss"
export IMAGE="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REPOSITORY}/${SERVICE_NAME}:$(git rev-parse --short HEAD)"
```

## 3) Configure project and APIs

```bash
gcloud config set project "${GCP_PROJECT_ID}"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud artifacts repositories describe "${ARTIFACT_REPOSITORY}" --location="${GCP_REGION}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${ARTIFACT_REPOSITORY}" \
  --repository-format=docker \
  --location="${GCP_REGION}" \
  --description="GSS container images"
```

## 4) Build container image

```bash
gcloud builds submit --tag "${IMAGE}" .
```

## 5) Deploy service

```bash
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --region "${GCP_REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars "GSS_PROVIDER_ENDPOINT=https://${SERVICE_NAME}-$(echo ${GCP_REGION} | tr - _)-$(gcloud config get-value project).a.run.app/v1,GSS_PROVIDER_HOST=0.0.0.0,GSS_PROVIDER_PORT=8080,GSS_COMPLIANCE_LEVEL=standard,GSS_CERTIFIED=false,GSS_TEST_SUITE_VERSION=0.2.2"
```

After deploy, Cloud Run prints the HTTPS URL (for example `https://gss-provider-xxxxx-ew.a.run.app`).

## 6) Smoke test

```bash
SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region "${GCP_REGION}" --format='value(status.url)')"
curl -s "${SERVICE_URL}/v1/describe"
```

## 6b) Use this endpoint with the CLI

The CLI defaults to `http://127.0.0.1:8000/v1` unless you override it.

Set one of the following before running `gss` commands:

```bash
# Global default for all shops
export GSS_DEFAULT_ENDPOINT="https://gss-provider-125211190390.europe-west4.run.app/v1"

# Or shop-specific override (recommended when mixing endpoints)
export GSS_SHOP_MOCKSHOP_LOCAL_ENDPOINT="https://gss-provider-125211190390.europe-west4.run.app/v1"
```

Then verify:

```bash
gss mockshop.local describe
```

## 7) Custom domain (optional)

To expose `api.globalsupportstandard.com`:

1. Open Cloud Run service -> **Manage Custom Domains**
2. Map `api.globalsupportstandard.com` to the service
3. Add DNS records shown by Google (usually CNAME)
4. Wait for certificate provisioning

## 8) Recommended production flags

- Set min instances to reduce cold starts:
  - `--min-instances 1`
- Set max instances to control spend:
  - `--max-instances 50`
- Use a dedicated service account:
  - `--service-account gss-runtime@${GCP_PROJECT_ID}.iam.gserviceaccount.com`
- Store secrets in Secret Manager (instead of plain env vars)

## 9) GitHub automation on push to `main`

This repository includes:

- `.github/workflows/deploy-cloud-run-main.yml`
- `.github/workflows/publish-on-main.yml`

Configure these repository secrets for Cloud Run deployment:

- `GCP_WORKLOAD_IDENTITY_PROVIDER` (OIDC provider resource name)
- `GCP_SERVICE_ACCOUNT` (deployer service account email)
- `GCP_PROJECT_ID`
- `GCP_REGION` (for example `europe-west4`)
- `CLOUD_RUN_SERVICE` (for example `gss-provider`)
- `ARTIFACT_REPOSITORY` (for example `gss`)

Package publishing on `main` is version-aware:

- if `pyproject.toml` version already exists on PyPI, publish is skipped
- if version is new, workflow publishes to TestPyPI then PyPI

