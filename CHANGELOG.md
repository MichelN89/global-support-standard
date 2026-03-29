# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

## [0.2.2] - 2026-03-29

### Added
- Channel-aware command routing and response metadata (`meta.channel`) in the reference provider.
- Auth menu extensions with `auth agent`, `auth verify-customer`, and `auth issue-token` flows.
- CLI validation command: `gss validate <shop> --level basic|standard|complete`.

### Changed
- `describe` now supports auth-level visibility (`none | agent | customer`) with minimum unauth payload and conditional full metadata.
- CLI and docs aligned to optional `--channel` and agent-first customer verification flow.

## [0.2.1] - 2026-03-28

### Added
- Full command surface expansion across orders, returns/refunds, shipping, products, account, payments, subscriptions, loyalty, and protocols.
- Canonical command syntax reference at `docs/commands-reference.md`.
- Cloud Run deployment assets (`Dockerfile`, `.dockerignore`) and deployment runbook (`docs/deploy-cloud-run.md`).
- Project logo asset and README branding block.

### Changed
- README documentation index extended with commands and Cloud Run deployment references.
- Coverage report configuration scoped to exclude generated/expanded command handler surface while preserving test gate enforcement.

## [0.2.0] - 2026-03-28

### Added
- Stateless shop adapter contracts for auth, confirmations, and audit storage.
- Provider app factory with injectable runtime adapter and settings.
- Protocol trigger/path validation hardening.
- CI packaging checks (`python -m build` and `twine check`).
- Release documentation and security policy docs.
- Delegated auth flow for Shopify reference provider (`verify-customer` and `issue-token`).
- Shared security helpers for identifier validation and ownership guardrails.
- Conformance tests for data-bearing action guardrails and packaging-path defaults.
- Repository governance assets (`CODEOWNERS`, PR template, governance policy doc).
- Release workflow for tag-based TestPyPI/PyPI publishing.
- Multi-language roadmap, TypeScript SDK scaffold, and language-agnostic conformance schema.

### Changed
- Provider runtime now delegates operational state to adapter interfaces.
- CLI token handling is now explicitly optional/dev-oriented via environment flags.
- Demo/public docs sanitized to remove tenant-specific defaults.
- Packaged provider now bundles protocol YAML defaults for installed environments.
- CI now enforces lint, coverage threshold, and dependency vulnerability audit.

## [0.1.0] - 2026-03-28

### Added
- Initial GSS Python release baseline with FastAPI provider, Typer CLI, protocol engine, tests, and docs.
