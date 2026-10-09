# Architecture

- Web/PWA: static HTML, CSS and JavaScript. Account data and API responses are not cached.
- API: FastAPI validation, loopback/bearer access gate, security headers, strategy registry, backtest endpoint and paper-only broker routes.
- Strategy core: deterministic parsing to a small typed schema. Optional Ollama output is validated as data.
- Engine: pure-Python EMA calculations and a long-only bar backtester with next-bar-open fills, explicit costs, trade ledger and drawdown.
- Storage: local SQLite for a single-user installation. Broker keys are not stored in SQLite.
- Worker: separate opt-in process with persisted strategies and bar checkpoints; phone shutdown does not stop a separate server worker.
- Broker adapter: protocol plus one Alpaca paper implementation. There is no live broker URL or live-order method.
- MCP: stdio tools for parsing, backtesting and listing strategies; no order-submission tool.

SQLite and a single bearer token are not a multi-tenant SaaS architecture. Cloud production requires OIDC/passkeys, per-user authorization, tenant-scoped PostgreSQL, KMS envelope encryption for broker credentials, a durable queue with idempotent jobs, isolated workers, persistent fill reconciliation, distributed rate limiting, per-tenant risk policy, observability, disaster recovery, and independent threat/load testing.
