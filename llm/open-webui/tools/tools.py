from __future__ import annotations

# Open WebUI loads a module containing a top-level `class Tools` and optional
# global `VALVES`. This aggregator exposes both zyra_cli_manifest and
# github_repo_access tools when using the folder-based integration.
from typing import Any

from .github_repo_access import VALVES as GH_VALVES
from .github_repo_access import Tools as _GitHubTools
from .zyra_cli_manifest import VALVES as ZYRA_VALVES
from .zyra_cli_manifest import Tools as _ZyraTools


def _dedupe_valves(*groups: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for grp in groups:
        for v in grp:
            name = v.get("name")
            if not isinstance(name, str):
                continue
            if name not in seen:
                seen[name] = v
    return list(seen.values())


# Merge both tools' VALVES for Open WebUI UI rendering; de-duplicate by name
VALVES = _dedupe_valves(ZYRA_VALVES, GH_VALVES)


class Tools:  # noqa: D401 - Simple aggregator
    """Aggregate zyra_cli_manifest and github_repo_access tool methods."""

    def __init__(self, valves: dict | None = None) -> None:  # pragma: no cover
        self.valves = valves
        self._zyra = _ZyraTools(valves)
        self._gh = _GitHubTools(valves)

    # zyra_cli_manifest passthroughs
    def zyra_cli_manifest(
        self,
        command_name: str | None = None,
        format: str = "json",
        details: str | None = None,
    ) -> Any:
        return self._zyra.zyra_cli_manifest(command_name, format, details)

    # github_repo_access passthroughs
    def github_get_file_or_directory(self, path: str, ref: str | None = None) -> Any:
        return self._gh.github_get_file_or_directory(path, ref)

    def github_list_commits(
        self,
        sha: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
    ) -> Any:
        return self._gh.github_list_commits(sha, per_page, page)

    def github_list_file_commits(self, path: str, sha: str | None = None) -> Any:
        return self._gh.github_list_file_commits(path, sha)

    def github_list_pull_requests(
        self,
        state: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
    ) -> Any:
        return self._gh.github_list_pull_requests(state, per_page, page)

    def github_list_branches(
        self, per_page: int | None = None, page: int | None = None
    ) -> Any:
        return self._gh.github_list_branches(per_page, page)

    def github_list_discussions(
        self, per_page: int | None = None, page: int | None = None
    ) -> Any:
        return self._gh.github_list_discussions(per_page, page)

    def github_get_discussion(self, discussion_number: int) -> Any:
        return self._gh.github_get_discussion(discussion_number)

    def github_list_issues(
        self,
        state: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
    ) -> Any:
        return self._gh.github_list_issues(state, per_page, page)

    def github_get_issue(self, issue_number: int) -> Any:
        return self._gh.github_get_issue(issue_number)

    def github_search_code(
        self,
        query: str,
        path: str | None = None,
        language: str | None = None,
        extension: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
    ) -> Any:
        return self._gh.github_search_code(
            query,
            path=path,
            language=language,
            extension=extension,
            per_page=per_page,
            page=page,
        )
