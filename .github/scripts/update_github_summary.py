#!/usr/bin/env python3
"""
Fetch GitHub repo language stats and update README with aggregated summary.
Uses GitHub API - no external API key needed (GITHUB_TOKEN from workflow).
"""
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def gh_request(url: str, token: str) -> dict | list:
    """Make authenticated request to GitHub API."""
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_all_repos(token: str, owner: str) -> list[dict]:
    """Fetch all public repos for the user (works with GITHUB_TOKEN)."""
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{owner}/repos?per_page=100&page={page}&type=owner"
        batch = gh_request(url, token)
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_repo_languages(token: str, owner: str, repo: str) -> dict[str, int]:
    """Fetch language bytes for a repo."""
    url = f"https://api.github.com/repos/{owner}/{repo}/languages"
    try:
        return gh_request(url, token)
    except HTTPError:
        return {}


def aggregate_languages(
    token: str, owner: str, repos: list[dict], exclude_repos: set[str] | None = None
) -> tuple[dict[str, int], str, str]:
    """
    Aggregate language bytes across all repos.
    Returns (lang_bytes, earliest_date, latest_date).
    """
    exclude = exclude_repos or set()
    lang_bytes: dict[str, int] = defaultdict(int)
    dates: list[datetime] = []

    for r in repos:
        name = r.get("name", "")
        full_name = r.get("full_name", "")
        if full_name in exclude or name in exclude:
            continue
        if r.get("fork"):
            continue
        created = r.get("created_at")
        updated = r.get("updated_at")
        if created:
            dates.append(datetime.fromisoformat(created.replace("Z", "+00:00")))
        if updated:
            dates.append(datetime.fromisoformat(updated.replace("Z", "+00:00")))

        langs = fetch_repo_languages(token, owner, name)
        for lang, bytes_count in langs.items():
            lang_bytes[lang] += bytes_count

    earliest = min(dates).strftime("%d %B %Y") if dates else "N/A"
    latest = max(dates).strftime("%d %B %Y") if dates else "N/A"
    return dict(lang_bytes), earliest, latest


def format_bytes(n: int) -> str:
    """Format bytes as human readable (e.g. 1.2 MB)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:,.1f} MB"
    if n >= 1_000:
        return f"{n / 1_000:,.1f} KB"
    return f"{n:,} B"


def make_bar(percent: float, width: int = 25) -> str:
    """Create a bar like >>>>>>>>>----------------"""
    filled = round(percent / 100 * width)
    return ">" * filled + "-" * (width - filled)


def build_summary(
    lang_bytes: dict[str, int], start_date: str, end_date: str
) -> str:
    """Build the repo summary text."""
    lines = []
    total = sum(lang_bytes.values())
    if total == 0:
        return "No language data available."

    lines.append(f"From: {start_date} - To: {end_date}")
    lines.append("")
    lines.append(f"Total: {format_bytes(total)} across all repos")
    lines.append("")

    sorted_langs = sorted(
        lang_bytes.items(), key=lambda x: -x[1]
    )
    for lang, bytes_count in sorted_langs:
        percent = 100 * bytes_count / total
        size_str = format_bytes(bytes_count)
        bar = make_bar(percent)
        lines.append(f"{lang:<25} {size_str:>12}     {bar}   {percent:5.2f} %")

    return "\n".join(lines)


def update_readme(summary: str, readme_path: str = "README.md") -> None:
    """Replace content between markers in README."""
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    start_marker = "<!--START_SECTION:waka-->"
    end_marker = "<!--END_SECTION:waka-->"

    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )
    replacement = f"{start_marker}\n```text\n{summary}\n```\n{end_marker}"

    if start_marker in content and end_marker in content:
        new_content = pattern.sub(replacement, content)
    else:
        insert_point = "## 📫 Let's Connect!"
        section = f"\n## 📊 Coding Stats\n\n{start_marker}\n```text\n{summary}\n```\n{end_marker}\n\n{insert_point}"
        new_content = content.replace(insert_point, section)

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN not set, skipping update")
        return

    repo_env = os.environ.get("GITHUB_REPOSITORY", "")
    owner = repo_env.split("/")[0] if "/" in repo_env else "ZejunZhou"
    current_repo = repo_env  # exclude profile repo from stats

    try:
        repos = fetch_all_repos(token, owner)
        lang_bytes, start_date, end_date = aggregate_languages(
            token, owner, repos, exclude_repos={current_repo}
        )
    except (HTTPError, URLError) as e:
        print(f"Failed to fetch GitHub data: {e}")
        return

    if not lang_bytes:
        print("No language data found")
        return

    summary = build_summary(lang_bytes, start_date, end_date)
    update_readme(summary)
    print("README updated with GitHub repo stats")


if __name__ == "__main__":
    main()
