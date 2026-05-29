# Repository Guidelines

## Project Structure & Module Organization
This is a Python 3.12 FastAPI service for reviewing, writing, translating, and exporting Markdown content with LLM-backed agents.

- `main.py` defines the FastAPI app, middleware, and router registration.
- `core/` contains shared configuration, LLM provider/model selection, and middleware.
- `labs/` contains the API router, service orchestration, helpers, providers, constants, and agent implementations.
- `labs/agents/<agent_name>/` groups each agent's `agent.py`, `prompts.py`, and `schema.py`.
- `labs/providers/github/` contains GitHub extraction logic used by code-example workflows.
- `tests/` contains pytest tests named `test_*.py`.
- `docs/specs/` and `docs/plans/` hold implementation notes and planning docs.
- `public/markdown/` and `public/pdf/` are runtime output locations; do not commit generated artifacts unless explicitly required.

## Build, Test, and Development Commands
Set up a local environment:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Run the API locally:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 3015
```

Run tests:

```bash
pytest
```

Build and run the Docker image:

```bash
docker build -t labs-reviewer-app .
docker run --env-file .env -p 3015:80 labs-reviewer-app
```

## Coding Style & Naming Conventions
Use standard Python style with 4-space indentation, type hints for public functions, and small service/helper methods. Keep imports grouped as standard library, third-party, then local modules. Name tests after behavior, for example `test_service_initialization_wires_role_models`. Keep agent modules consistent: `agent.py` for behavior, `schema.py` for Pydantic request/response models, and `prompts.py` for prompt text.

## Testing Guidelines
The project uses pytest. Prefer focused unit tests with `monkeypatch` for LLMs, environment variables, filesystem paths, and provider calls so tests do not require network access or real API keys. Add or update tests when changing routing, service orchestration, output paths, LLM configuration, GitHub provider behavior, or agent schemas.

## Commit & Pull Request Guidelines
Recent commits use short conventional-style prefixes such as `feat:` and `refactor:`. Keep commit subjects imperative and scoped to the behavior changed, for example `feat: add PDF output listing endpoint`.

Pull requests should include a concise summary, test results (`pytest` output or reason not run), linked issue/spec when applicable, and screenshots or sample API responses for endpoint/output changes. Note any new environment variables and update `.env.example`.

## Security & Configuration Tips
Never commit `.env`, API keys, or generated private content. Configure provider credentials with environment variables such as `OPENAI_API_KEY` and optional `GROQ_API_KEY`. When adding per-agent LLM settings, keep defaults centralized in `core/llm_config.py` and document new variables in `.env.example`.

## Rules
- Read `.codex/instructions.md` to specific rules of this system.