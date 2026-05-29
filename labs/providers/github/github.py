"""GitHub repository provider utilities."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

from .constants import (
    DEFAULT_GITHUB_API_TIMEOUT,
    DEFAULT_GITHUB_USER_AGENT,
    GITHUB_REPO_URL_PATTERN,
)


class GitHubProvider:
    """Fetches focused source context from GitHub repositories."""

    MAX_FILE_EXCERPT_CHARS = 2500
    MAX_FILES_PER_REPO = 3
    FOCUSED_FILE_PRIORITY = (
        "agent.py",
        "service.py",
        "router.py",
        "helper.py",
        "schema.py",
        "prompts.py",
        "config.py",
        "main.py",
    )

    def __init__(
        self,
        timeout: int = DEFAULT_GITHUB_API_TIMEOUT,
        user_agent: str = DEFAULT_GITHUB_USER_AGENT,
        logger: logging.Logger | None = None,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent
        self.logger = logger or logging.getLogger(__name__)

    def extract_repositories(self, text: str) -> list[str]:
        repositories: list[str] = []
        seen: set[str] = set()
        for owner, repo in GITHUB_REPO_URL_PATTERN.findall(text):
            normalized = f"{owner}/{repo.removesuffix('.git')}"
            if normalized not in seen:
                seen.add(normalized)
                repositories.append(normalized)
        return repositories

    def extract_focus_paths(self, text: str) -> list[str]:
        focus_paths: list[str] = []
        seen: set[str] = set()
        reading_focus_list = False

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                reading_focus_list = self._is_focus_heading(stripped)
                continue
            if not reading_focus_list:
                continue

            bullet_match = re.match(r"^\s*[-*+]\s+(.+?)\s*$", line)
            if not bullet_match:
                break

            focus_path = self._normalize_focus_path(bullet_match.group(1))
            if (
                not focus_path
                or focus_path.startswith("http://")
                or focus_path.startswith("https://")
                or focus_path in seen
            ):
                continue

            seen.add(focus_path)
            focus_paths.append(focus_path)

        return focus_paths

    def fetch_repo_context(
        self, repository: str, focus_paths: list[str] | None = None
    ) -> str:
        owner, repo = repository.split("/", maxsplit=1)
        repo_api = f"https://api.github.com/repos/{owner}/{repo}"
        repo_data = self._http_get_json(repo_api)
        default_branch = repo_data.get("default_branch") or "main"

        lines = [
            f"Repository: {repository}",
            f"Description: {repo_data.get('description') or 'N/A'}",
            f"Language: {repo_data.get('language') or 'N/A'}",
            f"Default branch: {default_branch}",
        ]

        try:
            tree_api = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
            tree_data = self._http_get_json(tree_api)
            tree_items = tree_data.get("tree", [])
        except Exception:
            tree_items = []

        candidate_paths = self._select_candidate_paths(tree_items, focus_paths or [])

        for path in candidate_paths:
            try:
                content_api = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
                content_data = self._http_get_json(content_api)
                decoded = self._decode_repo_file_content(
                    str(content_data.get("content", ""))
                )
                if not decoded.strip():
                    continue
                excerpt = decoded.strip()[: self.MAX_FILE_EXCERPT_CHARS]
                lines.append(f"File: {path}")
                lines.append(f"Language: {self._language_from_file_path(path)}")
                lines.append("Snippet:")
                lines.append("```")
                lines.append(excerpt)
                lines.append("```")
            except Exception:
                self.logger.info(
                    "provider=github | could not read file %s in %s",
                    path,
                    repository,
                )

        return "\n".join(lines)

    def _http_get_json(self, url: str) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self.user_agent,
        }
        github_token = os.getenv("GITHUB_TOKEN", "").strip()
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        request = Request(
            url,
            headers=headers,
        )
        with urlopen(request, timeout=self.timeout) as response:
            payload = response.read().decode("utf-8")
        return json.loads(payload)

    @staticmethod
    def _decode_repo_file_content(raw_content: str) -> str:
        if not raw_content:
            return ""
        return base64.b64decode(raw_content).decode("utf-8", errors="ignore")

    @staticmethod
    def _is_source_file(path: str) -> bool:
        lowered = path.lower()
        return lowered.endswith(
            (
                ".py",
                ".ts",
                ".tsx",
                ".js",
                ".jsx",
                ".go",
                ".java",
                ".kt",
                ".rs",
                ".yaml",
                ".yml",
            )
        )

    @classmethod
    def _is_candidate_source_file(cls, path: str) -> bool:
        if not cls._is_source_file(path):
            return False
        keywords = ("main", "app", "router", "route", "service", "handler", "config")
        return any(keyword in path.lower() for keyword in keywords)

    @staticmethod
    def _is_focus_heading(line: str) -> bool:
        normalized = re.sub(r"[^a-z0-9\s]", " ", line.lower())
        words = set(normalized.split())
        return (
            "focus" in words
            and "github" in words
            and bool({"folder", "folders", "path", "paths"} & words)
        )

    @staticmethod
    def _normalize_focus_path(raw_path: str) -> str:
        path = raw_path.strip().strip("`").strip()
        path = path.lstrip("/").rstrip("/")
        return path.strip()

    @staticmethod
    def _is_test_path(path: str) -> bool:
        lowered = path.lower()
        return (
            lowered.startswith("tests/")
            or "/tests/" in lowered
            or lowered.startswith("test_")
            or "/test_" in lowered
            or lowered.endswith("_test.py")
            or lowered.endswith(".test.ts")
            or lowered.endswith(".test.tsx")
            or lowered.endswith(".test.js")
            or lowered.endswith(".test.jsx")
            or lowered.endswith(".spec.ts")
            or lowered.endswith(".spec.tsx")
            or lowered.endswith(".spec.js")
            or lowered.endswith(".spec.jsx")
        )

    @staticmethod
    def _matches_focus_path(path: str, focus_path: str) -> bool:
        normalized_path = path.strip("/")
        normalized_focus = focus_path.strip("/")
        return (
            normalized_path == normalized_focus
            or normalized_path.startswith(f"{normalized_focus}/")
        )

    @classmethod
    def _select_candidate_paths(
        cls, tree_items: list[dict], focus_paths: list[str]
    ) -> list[str]:
        blob_paths = [
            str(item.get("path", ""))
            for item in tree_items
            if str(item.get("type", "")) == "blob"
        ]
        selected_paths: list[str] = []
        seen: set[str] = set()

        def add_path(path: str) -> None:
            if path and path not in seen and len(selected_paths) < cls.MAX_FILES_PER_REPO:
                seen.add(path)
                selected_paths.append(path)

        focus_matches = {
            focus_path: [
                path
                for path in blob_paths
                if cls._is_source_file(path)
                and cls._matches_focus_path(path, focus_path)
            ]
            for focus_path in focus_paths
        }

        for priority_name in cls.FOCUSED_FILE_PRIORITY:
            for paths in focus_matches.values():
                for path in paths:
                    if Path(path).name == priority_name:
                        add_path(path)

        for paths in focus_matches.values():
            for path in paths:
                if path not in seen:
                    add_path(path)

        for path in blob_paths:
            if cls._is_test_path(path):
                continue
            if cls._is_candidate_source_file(path):
                add_path(path)

        return selected_paths

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
