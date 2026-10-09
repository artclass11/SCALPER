# Roadmap

## Foundation release
- [x] Local-first black PWA
- [x] Constrained EMA crossover strategy DSL
- [x] Backtest metrics, trade ledger, fee and slippage assumptions
- [x] Local SQLite strategy registry
- [x] Alpaca paper-only adapter and limit-order checks
- [x] Explicitly opt-in separate paper worker
- [x] Optional loopback-only Ollama parser
- [x] MCP analysis tools
- [x] CI, dependency audit, CodeQL and Windows packaging workflow

## Required before a public SaaS launch
- [ ] OIDC/passkey authentication, roles, recovery and tenant isolation
- [ ] PostgreSQL migrations, backups and restore tests, tenant data controls
- [ ] KMS-backed broker credential vault and rotation
- [ ] Distributed queue, singleton strategy leases, idempotent jobs and fill reconciliation
- [ ] Multi-instance rate limits, abuse prevention and load tests
- [ ] Broker adapter certification suites and separately reviewed integrations
- [ ] Market calendar, data licensing and corporate action handling
- [ ] Fuzz/property tests, threat model, penetration test and independent audit
- [ ] Scale/failover/recovery tests at the actual target load
- [ ] Observability, alerting, SLOs, incident response and disaster recovery
- [ ] Reviewed SBOM, signed builds and release provenance
- [ ] Android APK build/signing and desktop smoke tests on clean systems

## Not in this release
Live-money order routing, public multi-user account linking, short selling, options/futures leverage, arbitrary model-generated code execution, and guarantees of profitability.
