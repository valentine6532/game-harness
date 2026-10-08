from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_FILE_LIMIT = 16_000
DEFAULT_TOTAL_LIMIT = 140_000


def run_git(root: Path, *args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return result.returncode, result.stdout.strip()


def repository_root(start: Path) -> Path:
    code, value = run_git(start, "rev-parse", "--show-toplevel")
    if code == 0 and value:
        return Path(value).resolve()
    return start.resolve()


def read_document(path: Path, root: Path, limit: int) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        stat = path.stat()
    except OSError as exc:
        return {
            "path": path.relative_to(root).as_posix(),
            "error": str(exc),
            "content": "",
            "truncated": False,
        }
    return {
        "path": path.relative_to(root).as_posix(),
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "content": text[:limit],
        "truncated": len(text) > limit,
    }


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.resolve(strict=False)).casefold()
        if key not in seen and path.is_file():
            seen.add(key)
            result.append(path)
    return result


def select_documents(root: Path) -> list[tuple[str, Path]]:
    selected: list[tuple[str, Path]] = []

    for name in ("WORKS.md", "README.md", "AGENTS.md", "CLAUDE.md"):
        path = root / name
        if path.is_file():
            selected.append(("project", path))

    if (root / "works").is_dir():
        for path in sorted((root / "works").glob("*/EPISODES.md")):
            selected.append(("episode-index", path))
        for path in sorted((root / "works").glob("*/SERIES.md")):
            selected.append(("series", path))

    progress_paths: list[Path] = []
    for base_name in ("_workspace", "workspace"):
        base = root / base_name
        if base.is_dir():
            progress_paths.extend(base.rglob("progress.md"))
    progress_paths = sorted(
        unique_paths(progress_paths),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )[:16]
    selected.extend(("progress", path) for path in progress_paths)

    tasks = root / "tasks"
    if tasks.is_dir():
        task_paths = sorted(tasks.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True)[:8]
        selected.extend(("tasks", path) for path in task_paths)

    logs = root / "logs"
    if logs.is_dir():
        log_paths = sorted(
            logs.glob("????-??-??.md"),
            key=lambda item: (item.name, item.stat().st_mtime),
            reverse=True,
        )[:5]
        selected.extend(("daily-log", path) for path in log_paths)

    deduped: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for kind, path in selected:
        key = str(path.resolve(strict=False)).casefold()
        if key not in seen:
            seen.add(key)
            deduped.append((kind, path))
    return deduped


def git_evidence(root: Path) -> dict[str, Any]:
    inside_code, inside = run_git(root, "rev-parse", "--is-inside-work-tree")
    if inside_code != 0 or inside != "true":
        return {"available": False}

    _, branch = run_git(root, "branch", "--show-current")
    _, head = run_git(root, "rev-parse", "--short", "HEAD")
    _, status = run_git(root, "status", "--short", "--branch")
    _, diff_stat = run_git(root, "diff", "--stat")
    _, staged_stat = run_git(root, "diff", "--cached", "--stat")
    _, log_text = run_git(
        root,
        "log",
        "-8",
        "--date=iso-strict",
        "--pretty=format:%h%x09%ad%x09%s",
    )
    return {
        "available": True,
        "branch": branch,
        "head": head,
        "status": status.splitlines() if status else [],
        "diff_stat": diff_stat.splitlines() if diff_stat else [],
        "staged_stat": staged_stat.splitlines() if staged_stat else [],
        "recent_commits": log_text.splitlines() if log_text else [],
    }


def collect(root: Path, file_limit: int, total_limit: int) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    used = 0
    for kind, path in select_documents(root):
        remaining = total_limit - used
        if remaining <= 0:
            break
        document = read_document(path, root, min(file_limit, remaining))
        document["kind"] = kind
        used += len(str(document.get("content") or ""))
        documents.append(document)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": {"name": root.name, "root": "."},
        "git": git_evidence(root),
        "documents": documents,
        "documents_truncated_by_total_limit": used >= total_limit,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect evidence for the repository session summary")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository path; defaults to current directory")
    parser.add_argument("--file-limit", type=int, default=DEFAULT_FILE_LIMIT)
    parser.add_argument("--total-limit", type=int, default=DEFAULT_TOTAL_LIMIT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.file_limit < 1 or args.total_limit < 1:
        print("limits must be positive", file=sys.stderr)
        return 2
    root = repository_root(args.root)
    payload = collect(root, args.file_limit, args.total_limit)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
