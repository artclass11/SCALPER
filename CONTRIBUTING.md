# Contributing

SCALPER is being built from original code in this repository. Do not copy code or strategy implementations from other projects unless their license and provenance are reviewed and required notices retained.

## Development

    pip install -e ".[dev,mcp]"
    ruff check .
    ruff format --check .
    pytest -q
    bandit -q -r scalper

Changes affecting order routing must preserve the paper-only host boundary, test rejection cases, avoid logging secrets, and never add live trading without a separate security review. Do not add generated Python execution, eval, exec, unsafe deserialization, or public endpoints that accept broker credentials in request bodies.

List new third-party dependencies with a reason and license in THIRD_PARTY_NOTICES.md. Do not commit downloaded model weights, broker data, credentials or copied upstream source. Contributors must have the right to license their work under the repository license.
