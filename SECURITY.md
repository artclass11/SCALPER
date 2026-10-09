# Security policy

Do not publish an exploit or include broker credentials, account identifiers, personal information or trading history in a public issue. Use GitHub private vulnerability reporting for this repository if it is enabled. Otherwise contact the repository owner privately with a minimal reproduction.

## Safety boundaries

- The included adapter is hard-wired to Alpaca's paper API host.
- Live-trading endpoints and live order code are not part of this release.
- The API binds to loopback by default and denies non-loopback requests when no bearer token is configured.
- Secrets must be provided by environment or a secret manager; never log them, commit them or put them in prompts.
- AI parser output is a validated strategy schema. Arbitrary generated code is never run.
- Kill switch and order-size checks are defense-in-depth, not guarantees against every trading loss.

## Before production use

A production deployment still needs independent threat modeling, user authentication and authorization, tenant isolation, a central secret manager/KMS, rate limits, key rotation, audit retention, encrypted backups, dependency pinning/SBOM, incident response, load testing and broker-specific operational review. Do not advertise this foundation release as independently audited or production-certified.
