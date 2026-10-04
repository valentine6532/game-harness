#!/usr/bin/env python3
"""파일 수정 직전에 실행되는 훅. 작업 인계 규칙(handoff.md)을 코드로 지키게 한다.

막는 경우:
- 자신의 작업 파일 없이 프로젝트 파일을 고치려 할 때
- 다른 작업이 잡고 있는 곳을 고치려 할 때
- 자신의 작업 파일 `건드리는 곳`에 적지 않은 곳을 고치려 할 때
- 다른 세션이 진행 중인 작업 파일을 고치려 할 때
- 다른 작업과 겹치는 `건드리는 곳`을 적으려 할 때

하네스가 적용되지 않은 프로젝트에서는 아무것도 하지 않는다. 예상하지 못한 오류가 나면
수정을 막지 않는다(종료 코드 2만 수정을 막는다).

표준 입력으로 Claude Code 또는 Codex의 훅 JSON을 받는다.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

WORK = Path(".game-harness") / "work"
ACTIVE = ("진행 중", "멈춤", "막힘")
TAKEOVER_OK = ("멈춤", "막힘")
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$|^\*\*\* Move to: (.+)$", re.M)


class Deny(Exception):
    pass


# ---------- 작업 파일 읽기 ----------

def field(text: str, name: str) -> str:
    match = re.search(rf"^\s*[-*]\s*{re.escape(name)}\s*:\s*(.*)$", text, re.M)
    return match.group(1).strip() if match else ""


def split_list(value: str) -> list[str]:
    items = [item.strip().strip("`").strip() for item in value.split(",")]
    return [item for item in items if item and item != "없음"]


def norm(path: str) -> str:
    """프로젝트 기준 상대 경로를 비교용으로 맞춘다. 빈 문자열은 프로젝트 전체다."""
    path = path.replace("\\", "/").strip()
    while path.startswith("./"):
        path = path[2:]
    path = path.strip("/")
    return "" if path == "." else path.casefold()


def under(path: str, claim: str) -> bool:
    return claim == "" or path == claim or path.startswith(claim + "/")


def overlaps(a: str, b: str) -> bool:
    return under(a, b) or under(b, a)


class Work:
    def __init__(self, work_id: str, text: str, owner: str | None):
        self.id = work_id
        self.owner = owner
        self.status = field(text, "상태")
        self.who = field(text, "담당")
        self.claims_raw = split_list(field(text, "건드리는 곳"))
        self.claims = [norm(c) for c in self.claims_raw]
        self.allowed = split_list(field(text, "겹침 허용"))

    @property
    def active(self) -> bool:
        # 상태를 못 읽은 파일도 살아 있는 작업으로 본다. 모르면 막는 쪽이 안전하다.
        return self.status != "끝남"

    def label(self) -> str:
        return f"{self.id}(담당: {self.who or '미상'}, 상태: {self.status or '미상'})"


def owners_dir(root: Path) -> Path:
    return root / WORK / ".local" / "owners"


def read_owner(root: Path, work_id: str) -> str | None:
    try:
        return (owners_dir(root) / work_id).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def write_owner(root: Path, work_id: str, session: str) -> None:
    owners_dir(root).mkdir(parents=True, exist_ok=True)
    (owners_dir(root) / work_id).write_text(session, encoding="utf-8")


def load_works(root: Path) -> list[Work]:
    works = []
    for path in sorted((root / WORK / "now").glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        works.append(Work(path.stem, text, read_owner(root, path.stem)))
    return works


# ---------- 훅 입력 ----------

def target_paths(data: dict) -> list[Path]:
    tool_input = data.get("tool_input") or {}
    cwd = Path(data.get("cwd") or os.getcwd())
    raw = []
    for key in ("file_path", "notebook_path"):
        if isinstance(tool_input.get(key), str):
            raw.append(tool_input[key])
    if data.get("tool_name") == "apply_patch":
        patch = tool_input.get("command") or tool_input.get("input") or ""
        if isinstance(patch, list):
            patch = "\n".join(str(part) for part in patch)
        raw += [a or b for a, b in PATCH_FILE.findall(patch)]
    return [Path(os.path.abspath(cwd / p.strip())) for p in raw]


def find_root(path: Path) -> Path | None:
    for parent in path.parents:
        if (parent / WORK / "now").is_dir():
            return parent
    return None


def new_content(data: dict, path: Path) -> str | None:
    """작업 파일을 고친 뒤의 내용. 알 수 없으면 None."""
    tool_input = data.get("tool_input") or {}
    if isinstance(tool_input.get("content"), str):
        return tool_input["content"]
    old, new = tool_input.get("old_string"), tool_input.get("new_string")
    if isinstance(old, str) and isinstance(new, str):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        return text.replace(old, new) if tool_input.get("replace_all") else text.replace(old, new, 1)
    return None


# ---------- 판단 ----------

HOW = "방법은 .game-harness/harness/core/handoff.md에 있다."


def check_work_file(root: Path, path: Path, session: str, data: dict, works: list[Work]) -> None:
    work_id = path.stem
    current = next((w for w in works if w.id == work_id), None)
    if current and current.owner and current.owner != session and current.status not in TAKEOVER_OK:
        raise Deny(
            f"작업 파일 {work_id}는 다른 세션이 진행 중인 작업이다({current.label()}). 고치지 않는다.\n"
            "그 세션이 이미 끝났거나 이 작업을 넘겨받아야 하면, 사용자에게 확인을 받은 뒤 "
            f"{(WORK / '.local' / 'owners' / work_id).as_posix()} 파일을 지우고 다시 시도한다."
        )
    text = new_content(data, path)
    if text is not None:
        mine = Work(work_id, text, session)
        if mine.active:
            for other in works:
                if other.id == work_id or not other.active or other.id in mine.allowed:
                    continue
                if other.owner == session:
                    continue
                hit = [(a, b) for a, a_raw in zip(mine.claims, mine.claims_raw)
                       for b, b_raw in zip(other.claims, other.claims_raw) if overlaps(a, b)]
                if hit:
                    raise Deny(
                        f"적으려는 `건드리는 곳`이 다른 작업 {other.label()}의 "
                        f"`건드리는 곳`({', '.join(other.claims_raw)})과 겹친다. 작업 파일을 이대로 만들지 않는다.\n"
                        "어디가 겹치는지 사용자에게 알리고, 기다릴지, 겹치지 않는 범위로 좁힐지, 그래도 진행할지 묻는다. "
                        f"사용자가 진행하라고 하면 작업 파일에 `- 겹침 허용: {other.id}` 줄을 넣는다. {HOW}"
                    )
    write_owner(root, work_id, session)


def check_project_file(root: Path, path: Path, session: str, works: list[Work]) -> None:
    rel = norm(path.relative_to(root).as_posix())
    shown = path.relative_to(root).as_posix()
    active = [w for w in works if w.active]
    mine = [w for w in active if w.owner == session]
    if not mine:
        unowned = [w.id for w in active if w.owner is None]
        hint = (
            f" 이어받을 작업이 now/에 있다면({', '.join(unowned)}) 그 작업 파일의 `담당`과 `마지막 갱신`을 고치면 넘겨받는다."
            if unowned else ""
        )
        raise Deny(
            f"{shown}을 고치기 전에 자신의 작업 파일이 필요하다. "
            f"{(WORK / 'now').as_posix()}/의 파일을 모두 읽고, `건드리는 곳`을 적은 자신의 작업 파일을 만든 뒤 다시 시도한다."
            f"{hint} {HOW}"
        )
    allowed = {work_id for w in mine for work_id in w.allowed}
    for other in active:
        if other.owner == session or other.id in allowed:
            continue
        for claim, raw in zip(other.claims, other.claims_raw):
            if under(rel, claim):
                raise Deny(
                    f"{shown}은 다른 작업 {other.label()}이 잡고 있는 곳({raw})이다. 고치지 않는다.\n"
                    "사용자에게 알리고, 기다릴지, 겹치지 않는 부분만 할지, 그래도 진행할지 묻는다. "
                    f"사용자가 진행하라고 하면 자신의 작업 파일에 `- 겹침 허용: {other.id}` 줄을 넣는다. {HOW}"
                )
    if not any(under(rel, claim) for w in mine for claim in w.claims):
        declared = ", ".join(c for w in mine for c in w.claims_raw) or "없음"
        raise Deny(
            f"{shown}은 자신의 작업 파일 `건드리는 곳`({declared})에 적혀 있지 않다. "
            f"먼저 자신의 작업 파일({', '.join(w.id for w in mine)})의 `건드리는 곳`에 이 경로나 상위 폴더를 추가한 뒤 다시 시도한다."
        )


def check(data: dict) -> None:
    session = str(data.get("session_id") or "")
    if not session:
        return
    for path in target_paths(data):
        root = find_root(path)
        if root is None:
            continue
        rel = path.relative_to(root)
        inside = rel.parts[:2] == WORK.parts
        if inside and rel.parts[2:3] == ("now",) and path.suffix == ".md":
            check_work_file(root, path, session, data, load_works(root))
        elif rel.parts[:1] == (".game-harness",):
            # 설정, 예외, 보관함은 하네스 관리 명령과 사용자 요청으로 고치는 곳이라 막지 않는다.
            continue
        else:
            check_project_file(root, path, session, load_works(root))


def end_session(data: dict) -> None:
    """세션이 끝나면 그 세션의 담당 표시를 지워, 다음 세션이 바로 넘겨받을 수 있게 한다."""
    session = str(data.get("session_id") or "")
    start = Path(data.get("cwd") or os.getcwd())
    for parent in [start, *start.parents]:
        folder = owners_dir(parent)
        if not folder.is_dir():
            continue
        for record in folder.iterdir():
            try:
                if record.read_text(encoding="utf-8").strip() == session:
                    record.unlink()
            except OSError:
                pass
        return


def main() -> int:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        if data.get("hook_event_name") == "SessionEnd":
            end_session(data)
        else:
            check(data)
    except Deny as denied:
        sys.stderr.buffer.write(f"[game-harness] {denied}\n".encode("utf-8"))
        return 2
    except Exception:  # 훅의 오류로 정상 작업을 막지 않는다.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
