# Security policy

Do not publish an exploit or include broker credentials, account identifiers, personal information or trading history in a public issue. Use GitHub private vulnerability reporting for this repository if it is enabled. Otherwise contact the repository owner privately with a minimal reproduction.

## Safety boundaries

- The broker adapter is fixed to Alpaca's paper trading host; no live-order route is included.
- The default server bind is loopback-only.
- When SCALPER_API_TOKEN is configured, every protected API request must present it, including requests that arrive from localhost through a reverse proxy.
- Never expose the local server through a reverse proxy without setting a long random SCALPER_API_TOKEN and configuring TLS/access controls at the gateway.
- Credentials must be provided by environment or a secret manager; never log them, commit them or put them in prompts.
- AI parser output is a validated strategy schema. Arbitrary generated code is never run.
- Client order IDs and broker reconciliation help prevent duplicate orders after timeouts, but do not replace operational monitoring or reconciliation.
- Risk checks are defense-in-depth, not guarantees against every trading loss.

## Before production use

A production deployment still needs independent threat modeling, user authentication and authorization, tenant isolation, a central secret manager/KMS, rate limits, key rotation, audit retention, encrypted backups, dependency pinning/SBOM, incident response, load testing and broker-specific operational review. Do not advertise this foundation release as independently audited or production-certified.
