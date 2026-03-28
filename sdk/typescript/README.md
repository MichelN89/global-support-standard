# TypeScript SDK Scaffold

This directory is a non-blocking scaffold for a future TypeScript implementation of GSS client/provider contracts.

## Scope (Current)

- Define package layout and release target.
- Document contract mapping to existing language-agnostic schemas.
- Prepare CI/test hooks for future conformance tests.

## Proposed Package Layout

```text
sdk/typescript/
  package.json
  tsconfig.json
  src/
    index.ts
    types/
    client/
    provider/
  tests/
```

## Initial Milestones

1. Implement typed envelope + error contracts from `schemas/`.
2. Implement client transport with required GSS headers.
3. Add conformance tests against `schemas/conformance/agent-delegation-checklist.json`.
4. Publish prerelease package after CI and contract tests are green.

Python remains the production release path while this scaffold evolves.
