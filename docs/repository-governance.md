# Repository Governance

This document defines required governance controls for production-safe collaboration on this repository.

## Branch Protection (main)

Configure branch protection for `main` with the following required settings:

1. Require a pull request before merging.
2. Require at least 1 approving review.
3. Require all review conversations to be resolved.
4. Require branches to be up to date before merge.
5. Require status checks to pass before merge.
6. Disallow force pushes.
7. Disallow branch deletion.

Recommended optional settings:

- Require signed commits.
- Restrict push permissions to maintainers.

## Required Status Checks

Require the following checks on `main`:

- `lint-ruff`
- `tests-py3.11`
- `tests-py3.12`
- `coverage-threshold`
- `package-check`
- `dependency-audit`

## Ownership and Review

Critical paths are protected via CODEOWNERS in `.github/CODEOWNERS`:

- workflow and packaging infrastructure
- core contracts and provider runtime
- authorization/security model docs

Changes to those paths must be reviewed by repository owners.

## Pull Request Quality Gate

All pull requests should use `.github/pull_request_template.md` and include:

- security impact statement
- test/validation evidence
- documentation updates for user-facing changes

## Anti-Troll / Anti-Break Principles

- No direct pushes to `main`.
- No unreviewed workflow changes.
- No secret material or local-only files in commits.
- Merge only when all required checks are green.
