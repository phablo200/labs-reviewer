# Labs Reviewer API

FastAPI service that turns raw Markdown lab notes into reviewed technical posts. The workflow uses LLM-backed agents to review and improve the content, enrich it with repository-grounded code examples, generate metadata, translate it to Brazilian Portuguese, and export Markdown/PDF outputs.

## Features

- Accept UTF-8 Markdown uploads for asynchronous review.
- Run specialized agents for writing, review, code examples, metadata, and translation.
- Generate English reviewed Markdown plus a pt-BR translated Markdown file.
- Render generated Markdown files to PDF.
- List generated Markdown and PDF outputs through API endpoints.
- Configure global or per-agent LLM provider, model, and temperature values.

## Project Structure

- `main.py`: FastAPI app entrypoint, CORS setup, middleware, and router registration.
- `core/`: shared settings, required-header middleware, and LLM configuration.
- `labs/router.py`: `/labs` and `/outputs` API routes.
- `labs/service.py`: orchestration layer for the review/export workflow.
- `labs/agents/`: specialized agent implementations, prompts, and schemas.
- `labs/providers/github/`: GitHub repository extraction used by code-example generation.
- `labs/helpers/`: Markdown and PDF persistence helpers.
- `public/markdown/`: generated Markdown output files.
- `public/pdf/`: generated PDF output files.
- `tests/`: pytest coverage for services, helpers, routers, providers, and LLM config.
- `docs/specs/` and `docs/plans/`: implementation specs and planning notes.

## Requirements

- Python 3.12+
- OpenAI API key for OpenAI-backed agents
- Groq API key for Groq-backed agents
- Optional GitHub token for repository extraction workflows

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your provider keys and runtime settings.

Common variables:

```bash
OPENAI_API_KEY=""
GROQ_API_KEY=""
GITHUB_TOKEN=""
OPENAI_MODEL=gpt-4o-mini
GROQ_MODEL=llama-3.1-8b-instant
LLM_POST_WRITER_PROVIDER=openai
LLM_REVIEWER_PROVIDER=groq
```

Per-agent variables follow this pattern:

```bash
LLM_<ROLE>_PROVIDER=openai|groq
LLM_<ROLE>_MODEL=<model-name>
LLM_<ROLE>_TEMPERATURE=0.3
```

Supported roles are `POST_WRITER`, `CODE_EXAMPLE`, `REVIEWER`, `METADATA`, and `TRANSLATOR`.

## Run Locally

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 3015
```

Health check:

```bash
curl http://127.0.0.1:3015/
```

## API Endpoints

### `POST /labs/review`

Uploads a UTF-8 `.md` file and starts background processing.

```bash
curl -X POST http://127.0.0.1:3015/labs/review \
  -F "file=@notes.md"
```

Example response:

```json
{
  "message": "Processing started.",
  "output_file": "/path/to/public/markdown/notes_reviewd.md"
}
```

Generated files include:

- `public/markdown/<name>_reviewd.md`
- `public/markdown/<name>_reviewd_pt_br.md`
- `public/pdf/<name>_reviewd.pdf`
- `public/pdf/<name>_reviewd_pt_br.pdf`

### `GET /outputs/makdown`

Lists generated Markdown files. The path currently uses `makdown` to match the implemented route.

```bash
curl http://127.0.0.1:3015/outputs/makdown
```

### `GET /outputs/pdf`

Lists generated PDF files.

```bash
curl http://127.0.0.1:3015/outputs/pdf
```

## Tests

Run the full test suite:

```bash
pytest
```

Tests avoid real network calls by stubbing LLMs, providers, and filesystem paths where needed. Add tests when changing routes, service orchestration, output naming, LLM configuration, or provider behavior.

## Docker

```bash
docker build -t labs-reviewer-app .
docker run --env-file .env -p 3015:80 labs-reviewer-app
```

## Notes

- Only `.md` uploads are accepted by `/labs/review`.
- Uploaded files must be UTF-8 encoded.
- Generated posts include YAML frontmatter from the metadata agent.
- Do not commit `.env`, real API keys, or generated private content.
