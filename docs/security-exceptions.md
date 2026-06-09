# Security Exceptions Register

This file tracks temporary CI security exceptions. Every exception must include a reason, tracking issue, and expiry date.

## Active Exceptions

- **ID:** `CVE-2026-4539`
- **Scope:** `pip-audit` in CI/release publish workflows
- **Reason:** Temporary transitive dependency false-positive under review with upstream maintainers
- **Tracking:** https://github.com/Global-Support-Standard/global-support-standard/issues/17
- **Expires:** `2026-06-30`
- **Removal criteria:** Remove ignore once upstream fix lands and dependency version is upgraded
