import base64
import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .constants import GITHUB_REPO_URL_PATTERN

AGENT_NAME = "labs_post_writer"


def build_code_examples_context(examples_response) -> str:
    if not examples_response.examples:
        return ""

    lines = ["## Code Examples Context", examples_response.summary.strip()]
    for item in examples_response.examples:
        snippet = item.snippet.strip()
        if len(snippet) > 1200:
            snippet = snippet[:1200].rstrip() + "\n..."
        lines.extend(
            [
                f"- Repository: {item.repository}",
                f"- File: {item.file_path}",
                f"- Language: {item.language}",
                f"- Why it matters: {item.why_it_matters}",
                f"- Integration hint: {item.integration_hint}",
                "```",
                snippet,
                "```",
                "",
            ]
        )
    return "\n".join(lines).strip()


def extract_github_repositories(markdown: str) -> list[tuple[str, str]]:
    repositories: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for owner, repo in GITHUB_REPO_URL_PATTERN.findall(markdown):
        normalized = (owner, repo.removesuffix(".git"))
        if normalized not in seen:
            seen.add(normalized)
            repositories.append(normalized)
    return repositories


def http_get_json(url: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mebrain-blog-writer",
    }
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    request = Request(
        url,
        headers=headers,
    )
    with urlopen(request, timeout=10) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def build_repo_context(owner: str, repo: str, logger: logging.Logger) -> str:
    repo_api = f"https://api.github.com/repos/{owner}/{repo}"
    repo_data = http_get_json(repo_api)

    summary_lines = [
        f"Repository: {owner}/{repo}",
        f"Description: {repo_data.get('description') or 'N/A'}",
        f"Language: {repo_data.get('language') or 'N/A'}",
        (
            "Topics: " + ", ".join(repo_data.get("topics", [])[:10])
            if repo_data.get("topics")
            else "Topics: N/A"
        ),
        f"Default branch: {repo_data.get('default_branch') or 'N/A'}",
    ]

    readme_content = ""
    readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    try:
        readme_data = http_get_json(readme_url)
        encoded_content = readme_data.get("content", "")
        if encoded_content:
            readme_content = base64.b64decode(encoded_content).decode(
                "utf-8", errors="ignore"
            )
    except Exception:
        logger.info(
            "agent=%s | could not fetch README for %s/%s", AGENT_NAME, owner, repo
        )

    if readme_content:
        trimmed_readme = readme_content.strip()[:4000]
        summary_lines.append("README excerpt:")
        summary_lines.append(trimmed_readme)

    return "\n".join(summary_lines)


def enrich_context_with_repositories(context: str, logger: logging.Logger) -> str:
    repositories = extract_github_repositories(context)
    if not repositories:
        return context

    logger.info(
        "agent=%s | found %s github repository link(s)", AGENT_NAME, len(repositories)
    )

    repo_sections: list[str] = []
    for owner, repo in repositories:
        try:
            repo_sections.append(build_repo_context(owner, repo, logger))
        except HTTPError as exc:
            logger.warning(
                "agent=%s | could not fetch repository context for %s/%s (http=%s)",
                AGENT_NAME,
                owner,
                repo,
                exc.code,
            )
        except URLError as exc:
            logger.warning(
                "agent=%s | network error while fetching repository context for %s/%s (%s)",
                AGENT_NAME,
                owner,
                repo,
                exc.reason,
            )
        except TimeoutError:
            logger.warning(
                "agent=%s | timeout while fetching repository context for %s/%s",
                AGENT_NAME,
                owner,
                repo,
            )
        except Exception:
            logger.exception(
                "agent=%s | failed to fetch repository context for %s/%s",
                AGENT_NAME,
                owner,
                repo,
            )

    if not repo_sections:
        return context

    extra_context = (
        "\n\n## Repository Context (Fetched from GitHub)\n"
        "Use this information to improve technical accuracy of the post.\n\n"
        + "\n\n---\n\n".join(repo_sections)
    )
    return context + extra_context
