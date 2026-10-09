# Security model

## Assets
Broker credentials, account values, positions, order history, strategy definitions, and prompt text.

## Trust boundaries
- Browser to local API: no bearer token only for loopback clients. Non-loopback binds require SCALPER_API_TOKEN.
- API to Alpaca: paper host is a constant; credentials come from the server environment, never browser fields.
- API to local model: Ollama URL is loopback-only by default and remote URLs are rejected.
- Prompt to engine: prompt is parsed into validated data; generated Python is never run.
- PWA service worker: only static shell files are cached; API paths are not cached.

## Controls implemented
Strict request schemas, constrained strategy parameters and order quantities, explicit paper-order confirmation, sell-to-close only, order-notional/equity limits, optional kill switch, sanitized broker errors, CSP and browser security headers, no-store API responses, ignored environment/database files, and CI lint/audit jobs.

## Known limitations
No multi-user authentication, tenant boundary, central KMS integration, distributed rate limiting, encrypted database deployment, SIEM integration, automatic key rotation, verified backups, or comprehensive broker event reconciliation. This code is not independently audited. No software can guarantee that financial data can never be breached.
