# quant alpha

## Dependency management (uv)

This project uses [uv](https://github.com/astral-sh/uv) to manage dependencies and generate `uv.lock`. Ensure your local Python version is 3.12 (see `.python-version`).

Common commands:

- Install / sync dependencies: `uv sync`
- Add a runtime dependency: `uv add <package>`
- Add a development dependency: `uv add --dev <package>`

Quick sync example:

```bash
# If uv is not installed, visit https://docs.astral.sh/uv/getting-started/installation/ for more details.

# Sync all dependencies based on the lock file
uv sync
```
