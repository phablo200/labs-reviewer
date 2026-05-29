import re


GITHUB_REPO_URL_PATTERN = re.compile(
    r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:[/?#][^\s)]*)?"
)
DEFAULT_GITHUB_API_TIMEOUT = 10
DEFAULT_GITHUB_USER_AGENT = "labs-code-example-agent"
