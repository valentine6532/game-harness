#!/usr/bin/env python3
"""Install the harness-owned global capabilities and prepare project overrides.

No network or OS permission changes. Only recorded installation units are replaced;
unowned name collisions fail before any writes. A transaction stages all units and
rolls them back on failure. Project files are never part of a global transaction.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SCHEMA = 1
OWNER = "game-harness"
RUNTIME_FILES = ("global_runtime.py", "work_guard.py")


class RuntimeError(Exception):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def frontmatter(text: str) -> tuple[str, str]:
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not match:
        raise RuntimeError("Missing YAML frontmatter")
    return match.group(0), text[match.end():]


def metadata(text: str, field: str) -> str:
    head, _ = frontmatter(text)
    match = re.search(rf"^{re.escape(field)}:\s*(.+)$", head, re.M)
    if not match:
        raise RuntimeError(f"Missing {field} in frontmatter")
    value = match.group(1).strip()
    if value.startswith('"'):
        return json.loads(value)
    return value.strip("'")


def is_link(path: Path) -> bool:
    # Windows junctions are not reported as symlinks by every Python version.
    return path.is_symlink() or (path.exists() and bool(
        getattr(path.lstat(), "st_file_attributes", 0) & 0x400
    ))


def safe_path(path: Path, boundary: Path) -> Path:
    path, boundary = Path(os.path.abspath(path)), Path(os.path.abspath(boundary))
    if not path.is_relative_to(boundary) or path == boundary:
        raise RuntimeError(f"Path outside managed boundary: {path}")
    for parent in [path, *path.parents]:
        if is_link(parent):
            raise RuntimeError(f"Linked installation/override path is not allowed: {parent}")
        if parent == boundary:
            break
    return path


def project_root(start: Path) -> Path:
    start = start.resolve()
    if not start.is_dir():
        raise RuntimeError(f"Project directory does not exist: {start}")
    for parent in [start, *start.parents]:
        if (parent / ".game-harness").is_dir():
            return parent
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start,
                                capture_output=True, text=True, encoding="utf-8", timeout=5)
        if result.returncode == 0:
            return Path(result.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return start


class Runtime:
    def __init__(self, home: Path | None = None, plugin: Path | None = None):
        self.home = Path(home or os.environ.get("GAME_HARNESS_HOME") or Path.home()).absolute()
        self.state = self.home / ".agents" / "game-harness"
        self.manifest_path = self.state / "manifest.json"
        self.plugin = plugin

    def manifest(self) -> dict | None:
        safe_path(self.manifest_path, self.home)
        if not self.manifest_path.is_file():
            return None
        data = json.loads(self.manifest_path.read_text("utf-8"))
        if data.get("owner") != OWNER or data.get("schema") != SCHEMA:
            raise RuntimeError("Invalid global game-harness manifest")
        for unit, record in data["units"].items():
            self.destination(unit)
            for rel in record["files"]:
                if rel and (Path(rel).is_absolute() or Path(rel).drive or ".." in Path(rel).parts or "\\" in rel):
                    raise RuntimeError(f"Invalid manifest file: {rel}")
        return data

    def source(self) -> Path:
        if self.plugin:
            return self.plugin.resolve()
        beside = Path(__file__).resolve().parents[1]
        if (beside / "bundled").is_dir():
            return beside
        manifest = self.manifest()
        if manifest:
            return Path(manifest["pluginRoot"])
        raise RuntimeError("Run sync from the installed game-harness plugin first")

    def destination(self, unit: str) -> Path:
        group, _, name = unit.partition("/")
        if not NAME.fullmatch(name) and not (group == "runtime" and name + ".py" in RUNTIME_FILES):
            raise RuntimeError(f"Invalid managed unit: {unit}")
        roots = {
            "skills": self.home / ".agents" / "skills",
            "claude-skills": self.home / ".claude" / "skills",
            "agents": self.state / "agents",
            "claude-agents": self.home / ".claude" / "agents",
            "codex-agents": Path(os.environ.get("CODEX_HOME") or self.home / ".codex") / "agents",
            "runtime": self.state,
        }
        if group not in roots:
            raise RuntimeError(f"Invalid managed group: {group}")
        suffix = {"agents": ".md", "claude-agents": ".md", "codex-agents": ".toml",
                  "runtime": ".py"}.get(group, "")
        target = roots[group] / (name + suffix)
        # A custom CODEX_HOME is explicit configuration, not a manifest-controlled path.
        boundary = roots[group].parent if group == "codex-agents" else self.home
        return safe_path(target, boundary)

    def desired(self) -> tuple[dict, dict[str, dict[str, bytes]]]:
        source = self.source()
        plugin = json.loads((source / "plugin.json").read_text("utf-8"))
        if plugin.get("name") != OWNER:
            raise RuntimeError("Source is not the game-harness plugin")
        bundle = source / "bundled"
        skills, agents, units = [], [], {}
        for folder in sorted((bundle / "skills").iterdir()):
            if not folder.is_dir():
                continue
            if is_link(folder):
                raise RuntimeError(f"Linked bundled skill: {folder}")
            name = folder.name
            if not NAME.fullmatch(name):
                raise RuntimeError(f"Invalid skill name: {name}")
            text = (folder / "SKILL.md").read_text("utf-8")
            if metadata(text, "name") != name:
                raise RuntimeError(f"Skill metadata disagrees with folder: {name}")
            files = {}
            for path in sorted(folder.rglob("*")):
                if is_link(path):
                    raise RuntimeError(f"Linked bundle file: {path}")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    files[path.relative_to(folder).as_posix()] = path.read_bytes()
            units[f"skills/{name}"] = files
            head, _ = frontmatter(text)
            base = self.destination(f"skills/{name}") / "SKILL.md"
            wrapper = head + f"\nRead and follow the complete managed skill at `{base.as_posix()}`. " \
                "Run its project-override preparation before proceeding. Resolve resources and scripts " \
                "relative to that managed skill directory, not this discovery wrapper.\n"
            units[f"claude-skills/{name}"] = {"SKILL.md": wrapper.encode("utf-8")}
            skills.append(name)
        for path in sorted((bundle / "agents").glob("*.md")):
            if is_link(path) or not NAME.fullmatch(path.stem):
                raise RuntimeError(f"Invalid bundled agent: {path}")
            text = path.read_text("utf-8")
            name, description = metadata(text, "name"), metadata(text, "description")
            if name != path.stem:
                raise RuntimeError(f"Agent metadata disagrees with filename: {path}")
            units[f"agents/{name}"] = {"": text.encode("utf-8")}
            units[f"claude-agents/{name}"] = {"": text.encode("utf-8")}
            _, body = frontmatter(text)
            # JSON basic strings are valid TOML strings; inherit the parent's model and permissions.
            toml = "\n".join(f"{key} = {json.dumps(value, ensure_ascii=False)}"
                             for key, value in (("name", name), ("description", description),
                                                ("developer_instructions", body))) + "\n"
            units[f"codex-agents/{name}"] = {"": toml.encode("utf-8")}
            agents.append(name)
        for filename in RUNTIME_FILES:
            units[f"runtime/{Path(filename).stem}"] = {"": (source / "scripts" / filename).read_bytes()}
        manifest = {
            "owner": OWNER, "schema": SCHEMA, "version": plugin["version"],
            "pluginRoot": str(source), "skills": skills, "agents": agents,
            "units": {unit: {"files": {rel: digest(data) for rel, data in sorted(files.items())}}
                      for unit, files in sorted(units.items())},
        }
        return manifest, units

    def integrity(self, manifest: dict | None = None) -> dict:
        manifest = manifest or self.manifest()
        result = {"installed": manifest is not None, "version": None,
                  "missing": [], "modified": [], "untracked": []}
        if manifest is None:
            return result
        result["version"] = manifest["version"]
        for unit, record in manifest["units"].items():
            dest = self.destination(unit)
            expected = record["files"]
            for rel, checksum in expected.items():
                path = dest / rel if rel else dest
                shown = f"{unit}/{rel}" if rel else unit
                if not path.is_file():
                    result["missing"].append(shown)
                elif is_link(path) or digest(path.read_bytes()) != checksum:
                    result["modified"].append(shown)
            if "" not in expected and dest.is_dir():
                for path in dest.rglob("*"):
                    if "__pycache__" in path.parts or path.suffix == ".pyc":
                        continue
                    rel = path.relative_to(dest).as_posix()
                    if is_link(path) or (path.is_file() and rel not in expected):
                        result["untracked"].append(f"{unit}/{rel}")
        return result

    @contextlib.contextmanager
    def locked(self):
        safe_path(self.state, self.home)
        self.state.mkdir(parents=True, exist_ok=True)
        lock = self.state / "sync.lock"
        deadline = time.monotonic() + 10
        while True:
            try:
                handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Global sync is already running (or stale lock): {lock}")
                time.sleep(0.05)
        try:
            os.write(handle, str(os.getpid()).encode("ascii"))
            yield
        finally:
            os.close(handle)
            lock.unlink()

    def sync(self, repair: bool = False) -> dict:
        desired, units = self.desired()
        with self.locked():
            previous = self.manifest()
            old = previous["units"] if previous else {}
            damaged = self.integrity(previous)
            if repair and previous and desired["version"] != previous["version"]:
                raise RuntimeError("Repair source version differs; run sync to update instead")
            conflicts = [str(self.destination(unit)) for unit in units
                         if unit not in old and self.destination(unit).exists()]
            if conflicts:
                raise RuntimeError("Unowned global files already exist; nothing overwritten:\n" +
                                   "\n".join(conflicts))
            changed = [unit for unit in units if old.get(unit) != desired["units"][unit]
                       or any(item == unit or item.startswith(unit + "/")
                              for key in ("missing", "modified", "untracked") for item in damaged[key])]
            removed = sorted(set(old) - set(units))
            same_manifest = previous and all(previous.get(key) == value for key, value in desired.items())
            if not changed and not removed and same_manifest:
                return {"version": desired["version"], "changed": [], "removed": [],
                        "integrityBefore": damaged}
            # All data is ready before touching installed units. Backups live on each destination's
            # filesystem so renames also work with a CODEX_HOME on another drive.
            prepared, swapped = [], []
            manifest_backup = self.manifest_path.read_bytes() if previous else None
            try:
                for unit in [*changed, *removed]:
                    dest = self.destination(unit)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    transaction = Path(tempfile.mkdtemp(prefix=".game-harness-txn-", dir=dest.parent))
                    staged, backup = transaction / "new", transaction / "old"
                    prepared.append((dest, transaction, staged, backup))
                    if unit in units:
                        files = units[unit]
                        if "" in files:
                            staged.write_bytes(files[""])
                        else:
                            for rel, data in files.items():
                                path = staged / rel
                                path.parent.mkdir(parents=True, exist_ok=True)
                                path.write_bytes(data)
                for dest, transaction, staged, backup in prepared:
                    if dest.exists():
                        dest.rename(backup)
                    swapped.append((dest, backup))
                    if staged.exists():
                        staged.rename(dest)
                desired["updatedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                pending = self.state / "manifest.new"
                pending.write_bytes(json_bytes(desired))
                os.replace(pending, self.manifest_path)
            except BaseException:
                for dest, backup in reversed(swapped):
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    elif dest.exists():
                        dest.unlink()
                    if backup.exists():
                        backup.rename(dest)
                if manifest_backup is not None:
                    self.manifest_path.write_bytes(manifest_backup)
                elif self.manifest_path.exists():
                    self.manifest_path.unlink()
                raise
            finally:
                for _, transaction, _, _ in prepared:
                    if transaction.exists():
                        shutil.rmtree(transaction)
                (self.state / "manifest.new").unlink(missing_ok=True)
            return {"version": desired["version"], "changed": changed, "removed": removed,
                    "integrityBefore": damaged}

    def prepare(self, kind: str, name: str, start: Path) -> dict:
        if kind not in ("skill", "agent") or not NAME.fullmatch(name):
            raise RuntimeError("Invalid capability kind or name")
        manifest = self.manifest()
        group = kind + "s"
        if not manifest or name not in manifest[group]:
            raise RuntimeError(f"Not a managed {kind}: {name}; run sync first")
        state = self.integrity(manifest)
        if any(state[key] for key in ("missing", "modified", "untracked")):
            raise RuntimeError("Global installation is damaged; run repair before using capabilities: " +
                               json.dumps(state, ensure_ascii=False))
        root = project_root(start)
        override = safe_path(root / ".game-harness" / "overrides" / group / name / "override.md", root)
        override.parent.mkdir(parents=True, exist_ok=True)
        created = False
        template = f"# {name} 프로젝트 오버라이드\n\n" \
            f"<!-- game-harness-base: {json.dumps({'version': manifest['version'], 'hash': manifest['units'][f'{group}/{name}']['files'].get('SKILL.md' if kind == 'skill' else '')})} -->\n\n" \
            "<!-- 이 프로젝트에서 바꿀 지침만 작성합니다.\n" \
            "비어 있으면 전역 기본 지침을 그대로 따릅니다. 기본 본문을 복사하지 않습니다. -->\n\n" \
            "## 변경할 지침\n\n## 추가할 지침\n"
        try:
            with override.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(template)
            created = True
        except FileExistsError:
            pass
        content = override.read_text("utf-8")
        meaningful = re.sub(r"<!--.*?-->", "", content, flags=re.S)
        active = any(line.strip() and not line.lstrip().startswith("#") for line in meaningful.splitlines())
        base = self.destination(f"{group}/{name}")
        if kind == "skill":
            base = base / "SKILL.md"
        warnings = []
        baseline = re.search(r"<!-- game-harness-base: (.*?) -->", content)
        if active and baseline:
            try:
                previous = json.loads(baseline.group(1))
            except ValueError:
                previous = {}
            if not isinstance(previous, dict):
                previous = {}
            current = manifest["units"][f"{group}/{name}"]["files"].get("SKILL.md" if kind == "skill" else "")
            if previous.get("hash") != current:
                warnings.append(f"Base {kind} changed since {previous.get('version')}; review the active override. "
                                "After review, update the game-harness-base comment with the current version/hash.")
        for overrides in (root / ".game-harness" / "overrides").glob("*/*/override.md"):
            category, target = overrides.parent.parent.name, overrides.parent.name
            if category in ("skills", "agents") and target not in manifest[category]:
                warnings.append(f"No managed target for override: {overrides}")
        return {"project": str(root), "kind": kind, "name": name, "version": manifest["version"],
                "baseHash": manifest["units"][f"{group}/{name}"]["files"].get("SKILL.md" if kind == "skill" else ""),
                "base": str(base), "override": str(override), "created": created,
                "active": active, "instructions": content, "warnings": warnings}

    def protected(self, path: Path) -> str | None:
        manifest = self.manifest()
        if not manifest:
            return None
        path = Path(os.path.abspath(path))
        # Protect aliases and their resolved targets, and parent-directory deletes/moves.
        roots = [(self.state, "management files")]
        for unit in manifest["units"]:
            roots.append((self.destination(unit), unit))
        source = Path(manifest["pluginRoot"])
        # Installed plugin copies are protected; the upstream development checkout stays editable.
        if not (source.parent.parent / ".git").exists():
            roots.append((source, "installed plugin"))
        for root, label in roots:
            for target, protected in ((path, root), (path.resolve(), root.resolve())):
                if target == protected or target.is_relative_to(protected) or protected.is_relative_to(target):
                    return label
        return None


def prepare_instruction(kind: str, name: str) -> str:
    group = kind + "s"
    label = "스킬은" if kind == "skill" else "에이전트는"
    return f"""## 프로젝트 오버라이드와 전역 원본 보호

이 {label} game-harness가 관리하는 전역 원본이다. 실행 전에 `~/.agents/game-harness/global_runtime.py`로 다음을 실행한다(사용 가능한 Python 실행 파일을 사용한다).

```text
python <사용자 홈>/.agents/game-harness/global_runtime.py prepare {kind} {name} --project <현재 프로젝트 또는 작업 폴더>
```

명령이 반환한 `project`를 프로젝트 루트로 사용하고 `instructions`를 읽는다. 파일이 없으면 `.game-harness/overrides/{group}/{name}/override.md`에 빈 템플릿만 만들어진다. 사용자 요청을 우선하고, 로컬에서 명시한 항목만 기본 지침에 덮어 적용한다. 빈 템플릿은 동작을 바꾸지 않는다. 지정되지 않은 항목과 관련 자료는 기본 지침을 유지한다. 지침 변경은 실행 코드 자체를 변경하지 않는다.

전역의 문서·스크립트·설정·에이전트를 수정하거나 삭제하지 않는다. 새 발견·실험 기록·프로젝트 설정은 프로젝트 폴더에 남긴다. 다른 에이전트를 호출할 때 `project`의 절대 경로와 적용한 오버라이드 경로를 전달하고, 그 에이전트도 자신의 오버라이드를 준비하게 한다. 명령 실패 시 원인을 알리고 준비가 되기 전 작업을 진행하지 않는다. 공통 원본 개선은 설치본 대신 원본 저장소에서 한다.

"""


def hook(runtime: Runtime, data: dict) -> int:
    event = data.get("hook_event_name")
    if event == "SessionStart":
        result = runtime.sync()
        damaged = result["integrityBefore"]
        context = "game-harness 전역 스킬·에이전트는 관리 원본이다. 직접 수정·삭제하지 않는다. " \
            "스킬·에이전트를 사용할 때 각 시작 절차의 prepare 명령으로 현재 프로젝트 오버라이드를 " \
            "읽고 없으면 빈 템플릿을 만든다. 전역 갱신은 프로젝트 오버라이드를 변경하지 않는다."
        if result["changed"] or result["removed"]:
            context += f" 전역 설치본을 하네스 {result['version']}에 동기화했다."
        if any(damaged[key] for key in ("missing", "modified", "untracked")):
            context += " 전역 설치본의 누락·변경을 감지해 배포 원본으로 복구했다: " + json.dumps(damaged, ensure_ascii=False)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
                                                "additionalContext": context}}, ensure_ascii=False))
    elif event == "SubagentStart":
        name = data.get("agent_type", "").split(":")[-1]
        manifest = runtime.manifest()
        if manifest and name in manifest["agents"]:
            result = runtime.prepare("agent", name, Path(data.get("cwd") or Path.cwd()))
            print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
                "additionalContext": json.dumps(result, ensure_ascii=False)}}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="game-harness global capabilities")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("sync", "status", "repair", "hook"):
        sub.add_parser(command)
    p = sub.add_parser("prepare")
    p.add_argument("kind", choices=("skill", "agent"))
    p.add_argument("name")
    p.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    runtime = Runtime()
    try:
        if args.command == "hook":
            return hook(runtime, json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}"))
        if args.command in ("sync", "repair"):
            result = runtime.sync(repair=args.command == "repair")
        elif args.command == "prepare":
            result = runtime.prepare(args.kind, args.name, args.project)
        else:
            result = runtime.integrity()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(args.command == "status" and any(result[key] for key in ("missing", "modified", "untracked")))
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"[game-harness] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
