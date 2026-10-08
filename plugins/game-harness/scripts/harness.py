#!/usr/bin/env python3
"""게임 하네스 내용물(payload)을 게임 프로젝트에 복사하고 비교하는 도구.

표준 라이브러리만 쓴다. 이 파일의 위치를 기준으로 플러그인 루트와 payload를 찾는다.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = PLUGIN_ROOT / "payload"

HARNESS_DIR = ".game-harness"
BLOCK_BEGIN = "<!-- game-harness:begin (자동 관리 구역. 직접 수정하지 않는다) -->"
BLOCK_END = "<!-- game-harness:end -->"
BLOCK_RE = re.compile(r"<!-- game-harness:begin.*?<!-- game-harness:end -->", re.S)


class HarnessError(Exception):
    pass


def global_manager():
    spec = importlib.util.spec_from_file_location("game_harness_global", PLUGIN_ROOT / "scripts" / "global_runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------- 내용물(payload) ----------

def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def plugin_version() -> str:
    return read_json(PLUGIN_ROOT / "plugin.json")["version"]


def version_key(version: str) -> tuple:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def available_modules() -> list[str]:
    root = PAYLOAD / "modules"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def file_hash(path: Path) -> str:
    # 줄바꿈 차이(git autocrlf)로 수정된 것처럼 보이지 않도록 맞춘 뒤 계산한다.
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def payload_files(modules: list[str]) -> dict[str, Path]:
    """harness/ 기준 상대 경로 -> payload 안의 원본 파일."""
    unknown = [m for m in modules if m not in available_modules()]
    if unknown:
        raise HarnessError(
            f"없는 기능: {', '.join(unknown)} (선택 가능: {', '.join(available_modules()) or '없음'})"
        )
    roots = [PAYLOAD / "core"] + [PAYLOAD / "modules" / m for m in modules]
    files = {"CHANGELOG.md": PAYLOAD / "CHANGELOG.md"}
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                files[path.relative_to(PAYLOAD).as_posix()] = path
    return files


def changelog_sections() -> list[tuple[str, str]]:
    """(버전, 본문) 목록. '## 0.1.0 - 2026-10-04' 형식의 제목을 버전 구분으로 읽는다."""
    text = (PAYLOAD / "CHANGELOG.md").read_text(encoding="utf-8")
    parts = re.split(r"^## +v?(\d+(?:\.\d+)*)[^\n]*\n", text, flags=re.M)
    return [(parts[i], parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2)]


def changelog_between(old: str, new: str) -> list[tuple[str, str]]:
    low, high = sorted([version_key(old), version_key(new)])
    return [(v, body) for v, body in changelog_sections() if low < version_key(v) <= high]


# ---------- git ----------

def git(cwd: Path, *args: str, timeout: float | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def source_repo() -> Path | None:
    """플러그인이 원본 저장소 안에서 직접 실행되고 있으면 그 저장소 경로를 준다.

    설치 캐시에서 실행 중이면 None이다. 홈 폴더 전체가 git 저장소인 사용자도 있으므로,
    git 안에 있다는 것만으로 판단하지 않고 원본 저장소의 구조와 맞는지 확인한다.
    """
    top = git(PLUGIN_ROOT, "rev-parse", "--show-toplevel")
    if not top:
        return None
    repo = Path(top).resolve()
    if PLUGIN_ROOT != repo / "plugins" / PLUGIN_ROOT.name:
        return None
    if not (repo / ".claude-plugin" / "marketplace.json").is_file():
        return None
    return repo


def source_warnings() -> list[str]:
    """플러그인이 원본 저장소를 직접 읽는 경우, 태그되지 않은 내용이 섞이는지 확인한다."""
    if source_repo() is None:
        return []
    warnings = []
    if git(PLUGIN_ROOT, "status", "--porcelain", "--", "."):
        warnings.append("원본 저장소의 플러그인 폴더에 커밋되지 않은 변경이 있다.")
    tag = f"v{plugin_version()}"
    changed = git(PLUGIN_ROOT, "diff", "--name-only", tag, "HEAD", "--", ".")
    if changed is None:
        warnings.append(f"원본 저장소에 {tag} 태그가 없다. 아직 내보내지 않은 버전이다.")
    elif changed:
        warnings.append(f"{tag} 태그를 붙인 뒤 플러그인 내용이 바뀌었다. 버전을 올리지 않은 수정이 섞여 있다.")
    return warnings


def project_warnings(project: Path) -> list[str]:
    if git(project, "rev-parse", "--is-inside-work-tree") != "true":
        return ["이 프로젝트는 git 저장소가 아니다. 업데이트를 되돌릴 방법이 없다."]
    if git(project, "status", "--porcelain"):
        return ["커밋되지 않은 변경이 있다. 먼저 커밋해 두어야 업데이트만 따로 되돌릴 수 있다."]
    return []


def published_version() -> str | None:
    """GitHub 원본 저장소에 올라온 가장 높은 버전 태그. 확인할 수 없으면 None."""
    url = read_json(PLUGIN_ROOT / "plugin.json").get("repository")
    if not url:
        return None
    output = git(PLUGIN_ROOT, "ls-remote", "--tags", "--refs", url, "v*", timeout=15)
    tags = re.findall(r"refs/tags/v(\d+(?:\.\d+)*)$", output or "", flags=re.M)
    return max(tags, key=version_key) if tags else None


# ---------- 프로젝트 ----------

def manifest_path(project: Path) -> Path:
    return project / HARNESS_DIR / "manifest.json"


def load_manifest(project: Path) -> dict | None:
    path = manifest_path(project)
    return read_json(path) if path.is_file() else None


def require_manifest(project: Path) -> dict:
    manifest = load_manifest(project)
    if manifest is None:
        raise HarnessError("이 프로젝트에는 하네스가 적용되어 있지 않다. 먼저 apply를 실행한다.")
    return manifest


def installed_state(project: Path, manifest: dict) -> dict:
    """manifest 기록과 실제 harness/ 폴더를 비교한다."""
    root = project / HARNESS_DIR / "harness"
    recorded = manifest["files"]
    missing, modified = [], []
    for rel, digest in recorded.items():
        path = root / rel
        if not path.is_file():
            missing.append(rel)
        elif file_hash(path) != digest:
            modified.append(rel)
    actual = (
        {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
        if root.is_dir()
        else set()
    )
    return {
        "missing": sorted(missing),
        "modified": sorted(modified),
        "untracked": sorted(actual - set(recorded)),
    }


def compute_diff(project: Path, manifest: dict, modules: list[str]) -> dict:
    new_files = {rel: file_hash(path) for rel, path in payload_files(modules).items()}
    old_files = manifest["files"]
    old_version, new_version = manifest["harnessVersion"], plugin_version()
    state = installed_state(project, manifest)
    return {
        "installedVersion": old_version,
        "availableVersion": new_version,
        "direction": (
            "same" if version_key(old_version) == version_key(new_version)
            else "upgrade" if version_key(old_version) < version_key(new_version)
            else "downgrade"
        ),
        "modules": {"installed": manifest["modules"], "target": modules},
        "added": sorted(set(new_files) - set(old_files)),
        "removed": sorted(set(old_files) - set(new_files)),
        "changed": sorted(r for r in new_files if r in old_files and new_files[r] != old_files[r]),
        "locallyModified": state["modified"],
        "missing": state["missing"],
        "untracked": state["untracked"],
        "changelog": [
            {"version": v, "body": body} for v, body in changelog_between(old_version, new_version)
        ],
        "warnings": project_warnings(project) + source_warnings(),
    }


def has_changes(diff: dict) -> bool:
    keys = ("added", "removed", "changed", "locallyModified", "missing", "untracked")
    return diff["direction"] != "same" or any(diff[k] for k in keys)


def render_block(modules: list[str]) -> str:
    template = (PAYLOAD / "templates" / "AGENTS.block.md").read_text(encoding="utf-8")
    lines = [
        f"- `{HARNESS_DIR}/harness/modules/{m}/README.md`: {m} 작업을 할 때 읽는다."
        for m in modules
    ] or ["- 선택한 기능 없음."]
    body = template.replace("{{version}}", plugin_version()).replace("{{modules}}", "\n".join(lines))
    return f"{BLOCK_BEGIN}\n{body.strip()}\n{BLOCK_END}"


def write_agents_block(project: Path, modules: list[str]) -> str:
    path = project / "AGENTS.md"
    block = render_block(modules)
    if not path.is_file():
        path.write_text(f"# {project.name}\n\n{block}\n", encoding="utf-8", newline="\n")
        return "created"
    text = path.read_text(encoding="utf-8")
    if BLOCK_RE.search(text):
        updated = BLOCK_RE.sub(lambda _: block, text, count=1)
    else:
        updated = text.rstrip("\n") + "\n\n" + block + "\n"
    if updated == text:
        return "unchanged"
    path.write_text(updated, encoding="utf-8", newline="\n")
    return "updated"


def copy_template(name: str, dest: Path) -> bool:
    """프로젝트 소유 파일은 없을 때만 만든다."""
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PAYLOAD / "templates" / name, dest)
    return True


def install(project: Path, modules: list[str], previous: dict | None) -> dict:
    harness_root = project / HARNESS_DIR
    target = harness_root / "harness"
    files = payload_files(modules)

    # 새 내용을 옆 폴더에 다 만든 뒤 바꿔치기해서, 복사 중 실패해도 기존 것이 남게 한다.
    staging = harness_root / "harness.new"
    if staging.exists():
        shutil.rmtree(staging)
    for rel, src in files.items():
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    if target.exists():
        shutil.rmtree(target)
    staging.rename(target)

    created = []
    if copy_template("project.yaml", harness_root / "project.yaml"):
        created.append(f"{HARNESS_DIR}/project.yaml")
    if copy_template("overrides-README.md", harness_root / "overrides" / "README.md"):
        created.append(f"{HARNESS_DIR}/overrides/README.md")
    if copy_template("work-README.md", harness_root / "work" / "README.md"):
        created.append(f"{HARNESS_DIR}/work/README.md")
    copy_template("work-gitignore", harness_root / "work" / ".gitignore")
    for name in ("now", "done"):
        # 빈 폴더는 git에 올라가지 않으므로 자리를 지키는 파일을 둔다.
        keep = harness_root / "work" / name / ".gitkeep"
        if not keep.parent.exists():
            keep.parent.mkdir(parents=True)
            keep.touch()
            created.append(f"{HARNESS_DIR}/work/{name}/")
    if copy_template("CLAUDE.md", project / "CLAUDE.md"):
        created.append("CLAUDE.md")
    agents = write_agents_block(project, modules)

    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    history = list(previous["history"]) if previous else []
    history.append({
        "from": previous["harnessVersion"] if previous else None,
        "to": plugin_version(),
        "at": now,
    })
    manifest = {
        "harnessVersion": plugin_version(),
        "modules": modules,
        "appliedAt": now,
        "files": {rel: file_hash(target / rel) for rel in sorted(files)},
        "history": history,
    }
    manifest_path(project).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    notes = []
    claude_md = project / "CLAUDE.md"
    if "AGENTS.md" not in claude_md.read_text(encoding="utf-8"):
        notes.append("기존 CLAUDE.md가 AGENTS.md를 불러오지 않는다. `@AGENTS.md` 한 줄을 추가해야 한다.")
    return {"version": plugin_version(), "modules": modules, "created": created,
            "agentsMd": agents, "fileCount": len(files), "notes": notes}


# ---------- 출력 ----------

def print_list(title: str, items: list[str]) -> None:
    if items:
        print(f"\n{title} ({len(items)})")
        for item in items:
            print(f"  {item}")


def print_diff(diff: dict) -> None:
    label = {"same": "버전 같음", "upgrade": "새 버전 있음", "downgrade": "설치된 플러그인이 더 낮은 버전"}
    print(f"현재 버전: {diff['installedVersion']}")
    print(f"플러그인 버전: {diff['availableVersion']} ({label[diff['direction']]})")
    if diff["modules"]["installed"] != diff["modules"]["target"]:
        print(f"기능: {diff['modules']['installed']} -> {diff['modules']['target']}")
    for section in diff["changelog"]:
        print(f"\n[{section['version']} 변경 내용]\n{section['body']}")
    print_list("추가되는 파일", diff["added"])
    print_list("삭제되는 파일", diff["removed"])
    print_list("내용이 바뀌는 파일", diff["changed"])
    print_list("손으로 고쳐진 파일 (업데이트하면 덮어써진다)", diff["locallyModified"])
    print_list("없어진 파일 (업데이트하면 다시 생긴다)", diff["missing"])
    print_list("기록에 없는 파일 (업데이트하면 지워진다)", diff["untracked"])
    print_list("경고", diff["warnings"])
    if not has_changes(diff):
        print("\n차이 없음.")


# ---------- 명령 ----------

def cmd_status(args) -> int:
    project = args.project
    manifest = load_manifest(project)
    if manifest is None:
        result = {"applied": False, "availableVersion": plugin_version(),
                  "globalCapabilities": global_manager().Runtime(plugin=PLUGIN_ROOT).integrity(),
                  "availableModules": available_modules()}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("하네스가 적용되어 있지 않다.")
            print(f"플러그인 버전: {plugin_version()}")
            print(f"선택 가능한 기능: {', '.join(available_modules()) or '없음'}")
        return 0
    diff = compute_diff(project, manifest, manifest["modules"])
    latest = published_version()
    result = {"applied": True, "modules": manifest["modules"], "appliedAt": manifest["appliedAt"],
              "globalCapabilities": global_manager().Runtime(plugin=PLUGIN_ROOT).integrity(),
              "publishedVersion": latest, **diff}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"기능: {', '.join(manifest['modules']) or '없음'}")
    print(f"적용 시각: {manifest['appliedAt']}")
    print_diff(diff)
    if latest and version_key(latest) > version_key(plugin_version()):
        print(f"\nGitHub에 새 버전 v{latest}이 올라와 있다. 설치된 플러그인은 {plugin_version()}이다.")
        print("플러그인을 먼저 갱신해야 이 프로젝트에 적용할 수 있다.")
    return 0


def cmd_diff(args) -> int:
    manifest = require_manifest(args.project)
    modules = args.modules if args.modules is not None else manifest["modules"]
    diff = compute_diff(args.project, manifest, modules)
    if args.json:
        print(json.dumps(diff, ensure_ascii=False, indent=2))
    else:
        print_diff(diff)
    return 0


def cmd_apply(args) -> int:
    if load_manifest(args.project) is not None:
        print("이미 하네스가 적용되어 있다. 아무것도 바꾸지 않았다. 상태는 status, 갱신은 update를 쓴다.")
        return 0
    if not args.project.is_dir():
        raise HarnessError(f"프로젝트 폴더가 없다: {args.project}")
    result = install(args.project, args.modules or [], None)
    print(f"하네스 {result['version']} 적용 완료 (파일 {result['fileCount']}개)")
    print(f"기능: {', '.join(result['modules']) or '없음'}")
    print(f"AGENTS.md: {result['agentsMd']}")
    print_list("새로 만든 프로젝트 파일", result["created"])
    print_list("확인할 것", result["notes"] + project_warnings(args.project) + source_warnings())
    return 0


def cmd_update(args) -> int:
    manifest = require_manifest(args.project)
    modules = args.modules if args.modules is not None else manifest["modules"]
    diff = compute_diff(args.project, manifest, modules)
    if not has_changes(diff) and manifest["modules"] == modules:
        print("이미 최신이다. 바꿀 것이 없다.")
        return 0
    if not args.yes:
        print_diff(diff)
        print("\n아무것도 바꾸지 않았다. 사용자에게 위 차이를 보여주고 확인을 받은 뒤 --yes를 붙여 다시 실행한다.")
        return 2
    result = install(args.project, modules, manifest)
    print(f"하네스 {diff['installedVersion']} -> {result['version']} 업데이트 완료 (파일 {result['fileCount']}개)")
    print(f"AGENTS.md: {result['agentsMd']}")
    print_list("확인할 것", result["notes"])
    return 0


def cmd_check(args) -> int:
    """배포 전 점검: 두 설정 파일의 버전과 CHANGELOG 최신 항목이 일치하는지 본다."""
    problems = []
    version = plugin_version()
    claude = read_json(PLUGIN_ROOT / ".claude-plugin" / "plugin.json").get("version")
    if claude != version:
        problems.append(f"plugin.json({version})과 .claude-plugin/plugin.json({claude})의 버전이 다르다.")
    sections = changelog_sections()
    if not sections or sections[0][0] != version:
        top = sections[0][0] if sections else "없음"
        problems.append(f"CHANGELOG.md의 최신 항목({top})이 버전({version})과 다르다.")
    for required in ("core", "templates/AGENTS.block.md", "templates/CLAUDE.md",
                     "templates/project.yaml", "templates/overrides-README.md",
                     "templates/work-README.md", "templates/work-gitignore",
                     "core/tools/with_lock.py"):
        if not (PAYLOAD / required).exists():
            problems.append(f"payload/{required}가 없다.")
    try:
        module = global_manager()
        module.Runtime(home=Path(tempfile.gettempdir()) / "game-harness-check", plugin=PLUGIN_ROOT).desired()
    except Exception as error:
        problems.append(f"전역 제작 스킬·에이전트 묶음: {error}")
    if problems:
        print_list("문제", problems)
        return 1
    print(f"점검 통과: 버전 {version}, 기능 {', '.join(available_modules()) or '없음'}")
    return 0


def cmd_source(args) -> int:
    repo = source_repo()
    if repo is None:
        print("이 플러그인은 설치된 사본이다. 원본 저장소가 이 PC에 있는지 사용자에게 묻는다.")
        return 1
    print(repo)
    return 0


def modules_arg(value: str) -> list[str]:
    return sorted({m.strip() for m in value.split(",") if m.strip()})


def cmd_global(args) -> int:
    module = global_manager()
    runtime = module.Runtime(plugin=PLUGIN_ROOT)
    try:
        if args.command == "global-sync":
            result = runtime.sync()
        elif args.command == "global-repair":
            result = runtime.sync(repair=True)
        elif args.command == "override":
            result = runtime.prepare(args.kind, args.name, args.project)
        else:
            result = runtime.integrity()
            result["availableVersion"] = plugin_version()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(args.command == "global-status" and
                   any(result[key] for key in ("missing", "modified", "untracked")))
    except (OSError, ValueError, KeyError, module.RuntimeError) as error:
        raise HarnessError(str(error)) from error


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="게임 하네스 관리 도구")
    sub = parser.add_subparsers(dest="command", required=True)

    def project_command(name: str, func, help_text: str):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--project", type=Path, default=Path.cwd(), help="게임 프로젝트 폴더 (기본: 현재 폴더)")
        p.set_defaults(func=func)
        return p

    p = project_command("status", cmd_status, "적용 상태와 새 버전 여부를 보고한다")
    p.add_argument("--json", action="store_true")
    p = project_command("diff", cmd_diff, "업데이트하면 무엇이 바뀌는지 보여준다")
    p.add_argument("--modules", type=modules_arg, default=None)
    p.add_argument("--json", action="store_true")
    p = project_command("apply", cmd_apply, "하네스를 처음 적용한다")
    p.add_argument("--modules", type=modules_arg, default=None, help="쉼표로 구분한 기능 목록")
    p = project_command("update", cmd_update, "harness/를 플러그인 버전으로 바꾼다")
    p.add_argument("--modules", type=modules_arg, default=None)
    p.add_argument("--yes", action="store_true", help="사용자 확인을 받은 뒤에만 붙인다")
    sub.add_parser("check", help="배포 전 점검").set_defaults(func=cmd_check)
    sub.add_parser("source", help="원본 저장소 경로를 출력한다").set_defaults(func=cmd_source)
    for name in ("global-sync", "global-status", "global-repair"):
        sub.add_parser(name, help="전역 제작 스킬·에이전트 설치·검사·복구").set_defaults(func=cmd_global)
    p = project_command("override", cmd_global, "실행할 스킬·에이전트의 로컬 오버라이드를 준비한다")
    p.add_argument("kind", choices=("skill", "agent"))
    p.add_argument("name")

    args = parser.parse_args(argv)
    if hasattr(args, "project"):
        args.project = args.project.resolve()
    try:
        return args.func(args)
    except HarnessError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
