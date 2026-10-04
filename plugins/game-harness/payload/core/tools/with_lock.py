#!/usr/bin/env python3
"""한 번에 한 세션만 쓸 수 있는 것(엔진 에디터, 검증 실행 등)을 차례대로 쓰게 한다.

    python .game-harness/harness/core/tools/with_lock.py <이름> [--wait 초] -- <명령...>

같은 이름으로 실행 중인 명령이 있으면 끝날 때까지 기다렸다가 실행한다. 명령의 종료 코드를
그대로 돌려준다. 기다리다 시간이 넘으면 명령을 실행하지 않고 종료 코드 75로 끝난다.

프로젝트의 검증 실행기가 이미 요청을 줄 세워 처리한다면 이 도구는 필요 없다.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

LOCKS = Path(__file__).resolve().parents[3] / "work" / ".local" / "locks"
BUSY = 75


def alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        # Windows에서 os.kill(pid, 0)은 프로세스를 끝내 버리므로 쓰지 않는다.
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def holder(lock: Path) -> dict | None:
    try:
        return json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def acquire(lock: Path, wait: float, label: str) -> bool:
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait
    announced = False
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            info = holder(lock)
            if info is not None and not alive(int(info.get("pid", -1))):
                # 잠금을 잡은 프로세스가 사라졌다. 남은 잠금을 치우고 다시 잡는다.
                try:
                    lock.unlink()
                except OSError:
                    pass
                continue
            if not announced:
                what = info.get("command", "?") if info else "?"
                print(f"[with_lock] '{label}'을 다른 작업이 쓰는 중이다: {what}. 기다린다.", file=sys.stderr)
                announced = True
            if time.monotonic() >= deadline:
                return False
            time.sleep(1)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "since": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "command": " ".join(sys.argv[sys.argv.index("--") + 1:])}, handle, ensure_ascii=False)
        return True


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="같은 이름의 명령을 한 번에 하나씩만 실행한다")
    parser.add_argument("name", help="함께 쓰는 것의 이름. 예: unity-editor")
    parser.add_argument("--wait", type=float, default=1800, help="기다릴 최대 시간(초). 기본 1800")
    if "--" not in sys.argv:
        parser.error("실행할 명령을 -- 뒤에 적는다")
    split = sys.argv.index("--")
    args = parser.parse_args(sys.argv[1:split])
    command = sys.argv[split + 1:]
    if not command:
        parser.error("실행할 명령을 -- 뒤에 적는다")

    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in args.name)
    lock = LOCKS / f"{safe}.lock"
    if not acquire(lock, args.wait, args.name):
        print(f"[with_lock] {args.wait:.0f}초를 기다렸지만 '{args.name}'이 비지 않았다. 명령을 실행하지 않았다.",
              file=sys.stderr)
        return BUSY
    try:
        return subprocess.run(command).returncode
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
