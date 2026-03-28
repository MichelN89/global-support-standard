# Multi-Language Roadmap (Non-Blocking)

This roadmap keeps Python as the production release path while enabling additional language SDKs in parallel.

## Principles

1. Python release readiness must never be blocked by non-Python SDK progress.
2. Conformance requirements are language-agnostic and shared.
3. New SDKs must pass contract-focused tests before being considered supported.

## Current State

- Production path: Python (`global-support-standard` package)
- Shared conformance tests: `tests/conformance/`
- Shared schema contracts: `schemas/`
- TypeScript scaffold: `sdk/typescript/`

## Phased Adoption

### Phase A: Contract First (current)

- Keep schema and conformance behavior canonical in this repository.
- Use Python implementation as reference behavior.

### Phase B: TypeScript SDK Skeleton

- Establish package layout and public API shape.
- Provide typed command/request contracts and transport abstractions.
- No parity requirement with Python provider runtime in this phase.

### Phase C: Conformance Gate

- Add TypeScript test harness that validates:
  - data-bearing action guardrails
  - authorization metadata exposure in `describe`
  - fail-closed error semantics

### Phase D: Supported SDK Status

- Mark TypeScript SDK as supported only after passing conformance suite and publishing release notes.

## Acceptance Criteria For New Language SDKs

- Implements core request/response envelope contracts.
- Supports required auth headers and consumer identity metadata.
- Preserves required error-code semantics for guardrail failures.
- Includes CI checks and release process documentation.

## Release Independence

Python releases continue on their own cadence.  
TypeScript and future SDKs release independently with their own package registries and versions.
