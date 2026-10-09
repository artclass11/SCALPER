# Security model

## Assets
Broker credentials, account values, positions, order history, strategy definitions, and prompt text.

## Trust boundaries
- Browser to local API: loopback-only by default. Without a token, both the client address and Host header must be local. This blocks common reverse-proxy loopback bypass and DNS-rebinding cases.
- Protected deployments: if SCALPER_API_TOKEN is configured, every API request requires its bearer token, including requests that arrive from the server through a local reverse proxy. The UI's Unlock API action holds the token in JavaScript memory only; it is not stored in local/session storage.
- API to Alpaca: only fixed paper trading and market-data hosts are allowed. Credentials come from server environment and never browser fields.
- API to local model: Ollama URLs are loopback-only by default.
- Prompt to engine: prompt is parsed into a typed allow-list; generated Python is never run.
- Order retries: each submission uses a stable client order ID. The adapter reconciles by that ID after an ambiguous network error and rejects attempts to reuse an ID for different order parameters.
- PWA service worker: caches static shell assets only; API paths are not cached.

## Controls implemented
Strict request schemas, path-safe stock symbols, bounded input sizes, explicit paper-order confirmation, sell-to-close checks that reject short positions, order-notional/equity limits, optional kill switch, broker-response validation, bounded error messages, CSP and browser security headers, no-store API responses, private local database/file permissions, ignored environment/database files, and CI lint/audit/CodeQL jobs.

## Known limitations
No multi-user authentication, tenant boundary, central KMS integration, distributed rate limiting, encrypted database deployment, SIEM integration, automatic key rotation, verified backups, or full broker order/fill reconciliation. The local app is not independently audited. The worker is not high-availability, and deactivation cannot cancel an order already accepted by the broker. Host-header checks are defense-in-depth, not a replacement for configuring a long random API token and a correctly secured reverse proxy.

This release uses paper trading only and is not suitable for untrusted public SaaS users. No software can guarantee that financial data can never be breached.
