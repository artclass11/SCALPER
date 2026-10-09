# SCALPER

SCALPER is a clean-room, privacy-first algorithmic trading workbench. This release provides a minimal black PWA, constrained natural-language strategy creation, reproducible EMA-crossover backtests, local saved strategies, risk checks, an Alpaca paper-only adapter, optional local Ollama parsing, and MCP tools for compatible AI clients.

This is a foundation release, not a claim of institutional production readiness. Live-money orders, multi-user SaaS authentication, tenant isolation, and additional broker live execution are not enabled. Do not expose this single-user build directly to the public internet.

## Features

- Local-first web/PWA; API and account responses are never cached offline.
- Plain-language EMA crossover parsing into a validated schema. AI output is data only; arbitrary Python is never evaluated.
- Backtests with next-bar-open execution, fees, slippage, trade records and drawdown metrics.
- SQLite strategy registry. Strategies are inactive when saved.
- Opt-in separate paper worker; it can continue when the phone is off if the host and worker remain running.
- Alpaca account, market bars, positions and limit orders, hard-wired to the paper trading host.
- Stable client order IDs and reconciliation after uncertain broker responses to lower duplicate-order risk on retries.
- Optional Ollama-local parsing; no model weights are bundled. Check model-specific licenses.
- MCP tools for strategy specs, backtesting and listing saved strategies. MCP exposes no order-submission tool.
- Loopback defaults, protected API token support, security headers, CI/CodeQL/Dependabot workflows and Windows packaging configuration.

## Quick start

Requires Python 3.11 or newer.

    python -m venv .venv
    # Windows PowerShell: .venv\Scripts\Activate.ps1
    # macOS/Linux: source .venv/bin/activate
    python -m pip install --upgrade pip
    pip install -e ".[dev,mcp]"
    scalper

Open http://127.0.0.1:8000. No account or API keys are required to parse strategies, save them locally, or run backtests.

## Alpaca paper account

Create paper credentials in your Alpaca account and set them only in the server environment.

    # PowerShell
    $env:SCALPER_ALPACA_PAPER_KEY="your-paper-key"
    $env:SCALPER_ALPACA_PAPER_SECRET="your-paper-secret"
    scalper

    # macOS/Linux
    export SCALPER_ALPACA_PAPER_KEY="your-paper-key"
    export SCALPER_ALPACA_PAPER_SECRET="your-paper-secret"
    scalper

Credentials are never accepted from browser fields and are not persisted to SQLite. The adapter uses the official paper-trading host only. The manual order route accepts limit orders only, requires confirmation and risk checks, and permits sells only to reduce an existing long position. Market-data terms, eligibility, supported assets and fill behavior remain subject to Alpaca's terms and service.

## Protected and cloud deployments

For every reverse-proxy, LAN or public gateway deployment, configure a strong random token of at least 32 characters before exposing the service:

    # Linux/macOS
    export SCALPER_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(40))')"
    scalper --host 0.0.0.0

The browser UI has an Unlock API action. It keeps the bearer token in memory only for the current tab and does not write it into browser storage. Set TLS and access controls at the gateway too. Do not reuse one token across multiple SaaS customers; this release has no user identity or tenant isolation.

The API also checks the Host header when operating without a configured token to reduce common reverse-proxy and DNS-rebinding exposures. This is defense-in-depth, not an alternative to a token for any proxy deployment. The CLI refuses non-loopback binds unless the token is at least 32 characters.

## Paper automation when the phone is off

The worker is a separate process and is disabled unless explicitly enabled. Set this environment variable for both API and worker, configure paper credentials, and restart the processes.

    SCALPER_AUTOMATION_ENABLED=true
    scalper-worker

The UI requires explicit confirmation before activation. The worker reads persisted strategies and sends only paper limit orders. Keep the host, worker, database and broker connection running. Turning off the phone does not stop server-side automation; stopping the host or worker does. This foundation worker is not a high-availability scheduler and does not provide exchange-grade order/fill reconciliation. Review paper activity before relying on it.

## Optional local AI

Install Ollama separately, download a model whose license you have reviewed, then set SCALPER_OLLAMA_MODEL to the installed model name and SCALPER_OLLAMA_BASE_URL to http://127.0.0.1:11434. The base URL is restricted to loopback for privacy. If the model returns an unsupported or invalid strategy, validation rejects it. The deterministic parser works without any model.

## MCP, desktop and mobile

Install the MCP extra and run scalper-mcp. Configure Claude or another compatible MCP host to launch that command in the project virtual environment. The MCP tools are non-executing analysis tools. For a ChatGPT Actions-style integration, see integrations/openapi.yaml and expose it only behind an authenticated TLS gateway.

The Windows build is configured in packaging/scalper.spec and the manual GitHub Actions release workflow. A clean-machine Windows smoke test is still required before distribution. The PWA is installable on supported mobile/desktop browsers. An Android APK is not included yet; reproducible APK creation and signing remain roadmap work.

## Tests

    pip install -e ".[dev,mcp]"
    ruff check .
    pytest -q
    bandit -q -r scalper
    pip-audit

CI runs lint, unit and API tests, Bandit and dependency auditing; CodeQL analyzes the Python code. No CI test submits a broker order.

## Copyright and commercial use

The application's new code is intended to be original and is released under the existing MIT license. MIT permits commercial use and resale subject to its notice conditions, but it also permits others to use and redistribute the same code; it does not grant exclusivity or guarantee zero legal risk. SCALPER avoids copying strategy implementations from other repositories. Dependencies are declared rather than copied into the source tree. See THIRD_PARTY_NOTICES.md and docs/LEGAL_IP_POLICY.md.

Before commercial distribution, retain a complete dependency/license SBOM, review each model-weight license separately, confirm contributor rights, check trademarks, and obtain legal advice for target markets. Do not redistribute broker logos, market data, SDKs or model weights without checking their terms.

## Safety notice

SCALPER is software tooling, not financial advice. Backtests can contain modeling errors and cannot predict future returns. Paper fills can differ from live execution. This release has no live-trading route.
