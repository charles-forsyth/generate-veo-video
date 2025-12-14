# Contributing to Generate Veo Video

We love your input! We want to make contributing to this project as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features

## Workflow

1. **Fork the repo** and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite passes (`uv run pytest`).
5. Make sure your code lints (`uv run ruff check .`).
6. Issue that Pull Request!

## Development Setup

We use `uv` for dependency management.

```bash
# Install dependencies
uv sync --dev

# Run tests
uv run pytest

# Run linter
uv run ruff check .
```

## License
By contributing, you agree that your contributions will be licensed under its MIT License.
