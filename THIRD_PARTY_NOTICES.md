# Third-party notices and license inventory

SCALPER does not vendor third-party application source or model weights in this repository. Exact installed dependency versions should be captured at build time using a software bill of materials (SBOM) and checked with CI audit tools.

| Component | Purpose | License / terms handling |
|---|---|---|
| Python | Runtime | PSF license; obtain from official distribution |
| FastAPI | HTTP API | MIT |
| Starlette | ASGI framework, pulled by FastAPI | MIT |
| Uvicorn | ASGI server | BSD-3-Clause |
| Pydantic | Request/schema validation | MIT |
| HTTPX | HTTP client | BSD-3-Clause |
| cryptography | Optional encrypted-secret utility | Review exact version's upstream notices |
| MCP Python SDK (optional) | Model Context Protocol server | Review exact pinned version's upstream license |
| Ollama (optional, installed separately) | Local model runtime | Review runtime's current upstream license and build notices |
| Each downloaded model | Optional inference weights | Model-specific license, not covered by the runtime's license |

This is an initial inventory, not a generated exhaustive SBOM. Transitive dependency licenses, exact versions, model weights, market data, broker API terms, icons and trademarks require build-time verification. CI runs pip-audit for known dependency vulnerabilities; this is not a license review.

For commercial releases, publish a versioned SBOM and attribution notices, pin reviewed dependencies, archive source licenses, and review upgrades. “Open weights” does not mean unrestricted commercial use.
