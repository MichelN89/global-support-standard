# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

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
- Initial GSS Python MVP with FastAPI provider, Typer CLI, protocol engine, tests, and docs.
