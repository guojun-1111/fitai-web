# Contributing to FitAI-Web

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
git clone https://github.com/yourusername/fitai-web.git
cd fitai-web
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your LLM API key (DeepSeek or OpenAI-compatible)

# Run tests
pytest tests/ -v

# Start dev server
python server.py
```

## Project Structure

```
fitai-web/
├── server.py              FastAPI app entry point
├── config.py              Environment config loader
├── auth/                  Authentication (scrypt, stateless tokens)
├── providers/             LLM provider abstraction
├── agent/                 ReAct agent loop
├── tools/                 22 AI function-calling tools + DB layer
├── routers/               API route modules
├── fitai/analysis/        29 pure-Python algorithm modules
├── fitai/health_platforms/ Health data importers
├── static/                Vanilla JS SPA frontend
├── miniapp/               WeChat Mini-Program
├── tests/                 113 test functions
└── scripts/               Benchmark & utility scripts
```

## Code Conventions

- **Analysis modules** (`fitai/analysis/`): Pure functions only. Import only from `math` and `collections`. No DB access, no side effects, no numpy/scipy.
- **Database**: All functions in `tools/fitai_database.py` take `user_id` as first parameter for multi-tenant isolation.
- **New AI tools**: Define in `tools/tool_definitions.py`. Implement in `tools/fitai_tools.py`. Register in `tools/registry.py`.

## How to Add a New Algorithm

1. Create `fitai/analysis/your_algorithm.py`
2. Write pure functions — take data, return results. No side effects.
3. Add tests in `tests/test_analysis.py`
4. Add benchmark integration in `scripts/run_all_benchmarks.py` (optional)

## How to Add a New AI Tool

1. Add the tool definition (JSON schema) to `tools/tool_definitions.py`
2. Add the implementation function to `tools/fitai_tools.py`
3. Register in `tools/registry.py`
4. The agent will automatically pick it up

## Testing

```bash
# All tests
pytest tests/ -v

# Analysis only
pytest tests/test_analysis.py -v

# Single test
pytest tests/test_analysis.py::test_causal_discovery_pc_stable -v
```

## Pull Request Process

1. Fork the repo and create a branch from `main`
2. Add tests for new functionality
3. Ensure `pytest tests/ -v` passes
4. Update documentation if needed
5. Submit PR with a clear description

## Need Help?

- [GitHub Discussions](https://github.com/yourusername/fitai-web/discussions)
- [Discord](https://discord.gg/placeholder)
