"""Code example agent implementation."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from pathlib import Path
from urllib.error import HTTPError, URLError

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from core.llm_config import AgentRole, LLMConfig
from labs.providers.github.github import GitHubProvider

from .prompts import LabCodeExamplePrompt
from .schema import LabCodeExampleItem, LabCodeExampleRequest, LabCodeExampleResponse


class LabCodeExampleAgent:
    """Extracts practical code examples from repositories referenced in notes."""

    def __init__(
        self,
        llm: BaseChatModel | None = None,
        github_provider: GitHubProvider | None = None,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.agent_name = AgentRole.CODE_EXAMPLE
        self.llm = llm or LLMConfig.build_chat_model_for_agent(AgentRole.CODE_EXAMPLE)
        self.github_provider = github_provider or GitHubProvider()

    def _format_human_context(
        self,
        request: LabCodeExampleRequest,
        repositories: list[str],
        focus_paths: list[str],
        repo_context_sections: list[str],
    ) -> str:
        repos_text = "\n".join(f"- {repo}" for repo in repositories) or "- none"
        focus_paths_text = "\n".join(f"- {path}" for path in focus_paths) or "- none"
        sections_text = "\n\n---\n\n".join(repo_context_sections) or "No repository context available."
        return (
            f"Max examples: {request.max_examples}\n"
            f"Repositories:\n{repos_text}\n\n"
            f"Focus paths:\n{focus_paths_text}\n\n"
            "Original notes context:\n"
            f"{request.notes_context}\n\n"
            "Fetched repository context:\n"
            f"{sections_text}"
        )

    @staticmethod
    def _language_from_file_path(file_path: str) -> str:
        suffix = Path(file_path).suffix.lower()
        return {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".go": "go",
            ".java": "java",
            ".kt": "kotlin",
            ".rs": "rust",
            ".yaml": "yaml",
            ".yml": "yaml",
        }.get(suffix, "text")

    @staticmethod
    def _extract_context_file_paths(repo_context_sections: list[str]) -> list[str]:
        file_paths: list[str] = []
        seen: set[str] = set()
        for section in repo_context_sections:
            for line in section.splitlines():
                if not line.startswith("File: "):
                    continue
                file_path = line.removeprefix("File: ").strip()
                if file_path and file_path not in seen:
                    seen.add(file_path)
                    file_paths.append(file_path)
        return file_paths

    @classmethod
    def _normalize_response_data(
        cls,
        response_data: dict,
        repositories: list[str],
        repo_context_sections: list[str],
    ) -> dict:
        examples = response_data.get("examples", [])
        if not isinstance(examples, list):
            response_data["examples"] = []
            return response_data

        default_repository = repositories[0] if repositories else ""
        context_file_paths = cls._extract_context_file_paths(repo_context_sections)
        normalized_examples: list[dict] = []

        for index, example in enumerate(examples):
            if not isinstance(example, Mapping):
                continue
            normalized = dict(example)
            snippet = str(normalized.get("snippet", "")).strip()
            if not snippet:
                continue

            fallback_file_path = (
                context_file_paths[index]
                if index < len(context_file_paths)
                else context_file_paths[0] if context_file_paths else "unknown"
            )
            normalized.setdefault("repository", default_repository)
            normalized.setdefault("file_path", fallback_file_path)
            normalized.setdefault(
                "language", cls._language_from_file_path(normalized["file_path"])
            )
            normalized.setdefault(
                "why_it_matters",
                "Shows a concrete implementation detail from the fetched repository context.",
            )
            normalized.setdefault(
                "integration_hint",
                "Use this snippet as a repository-backed example in the technical lab.",
            )
            normalized_examples.append(normalized)

        response_data["examples"] = normalized_examples
        return response_data

    def extract_examples(self, request: LabCodeExampleRequest) -> LabCodeExampleResponse:
        repositories = list(
            dict.fromkeys(
                request.repositories
                + self.github_provider.extract_repositories(request.notes_context)
            )
        )
        focus_paths = self.github_provider.extract_focus_paths(request.notes_context)
        if not repositories:
            return LabCodeExampleResponse(
                examples=[],
                summary="No GitHub repositories found in notes context.",
                warnings=["No repositories detected."],
            )

        warnings: list[str] = []
        repo_context_sections: list[str] = []
        for repository in repositories:
            try:
                repo_context_sections.append(
                    self.github_provider.fetch_repo_context(repository, focus_paths)
                )
            except HTTPError as exc:
                warnings.append(f"Could not fetch {repository} (http={exc.code}).")
            except URLError as exc:
                warnings.append(f"Network error for {repository} ({exc.reason}).")
            except TimeoutError:
                warnings.append(f"Timeout while fetching {repository}.")
            except Exception:
                self.logger.exception(
                    "agent=%s | failed to fetch context for %s",
                    self.agent_name,
                    repository,
                )
                warnings.append(f"Unexpected fetch error for {repository}.")

        if not repo_context_sections:
            return LabCodeExampleResponse(
                examples=[],
                summary="Repository context could not be fetched.",
                warnings=warnings or ["No repository context available."],
            )

        messages = [
            SystemMessage(content=LabCodeExamplePrompt.build_system_prompt()),
            HumanMessage(
                content=self._format_human_context(
                    request, repositories, focus_paths, repo_context_sections
                )
            ),
        ]

        try:
            structured_llm = self.llm.with_structured_output(LabCodeExampleResponse)
            response = structured_llm.invoke(messages)
        except Exception:
            self.logger.exception(
                "agent=%s | structured output failed", self.agent_name
            )
            return LabCodeExampleResponse(
                examples=[],
                summary="Failed to generate code examples.",
                warnings=warnings + ["Structured generation failed."],
            )

        if isinstance(response, Mapping):
            response_data = dict(response)
        else:
            response_data = {
                "examples": getattr(response, "examples", []),
                "summary": getattr(response, "summary", ""),
                "warnings": getattr(response, "warnings", []),
            }
        response_data = self._normalize_response_data(
            response_data, repositories, repo_context_sections
        )

        try:
            parsed = LabCodeExampleResponse.model_validate(response_data)
        except Exception:
            self.logger.exception(
                "agent=%s | invalid structured response", self.agent_name
            )
            return LabCodeExampleResponse(
                examples=[],
                summary="Invalid structured response for code examples.",
                warnings=warnings + ["Invalid model output for code examples."],
            )

        combined_warnings = warnings + parsed.warnings
        return LabCodeExampleResponse(
            examples=[LabCodeExampleItem.model_validate(item) for item in parsed.examples],
            summary=parsed.summary,
            warnings=combined_warnings,
        )
