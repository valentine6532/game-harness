"""work_guard.py에 훅 입력을 넣어 허용과 거부를 확인하는 시험."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / "plugins" / "game-harness" / "scripts" / "work_guard.py"
LOCK = REPO / "plugins" / "game-harness" / "payload" / "core" / "tools" / "with_lock.py"

WORK_FILE = """# {title}

- 작업 ID: {id}
- 상태: {status}
- 담당: claude
- 건드리는 곳: {claims}
{extra}
"""


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.now = self.root / ".game-harness" / "work" / "now"
        self.now.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def hook(self, session, tool, tool_input, event="PreToolUse", cwd=None):
        payload = {"session_id": session, "cwd": str(cwd or self.root), "hook_event_name": event,
                   "tool_name": tool, "tool_input": tool_input}
        result = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload).encode("utf-8"),
                                capture_output=True)
        return result.returncode, result.stderr.decode("utf-8")

    def edit(self, session, rel):
        return self.hook(session, "Edit", {"file_path": str(self.root / rel), "old_string": "a", "new_string": "b"})

    def work_text(self, work_id, claims, status="진행 중", extra=""):
        return WORK_FILE.format(title=work_id, id=work_id, status=status, claims=claims, extra=extra)

    def start_work(self, session, work_id, claims, status="진행 중", extra=""):
        """세션이 Write로 작업 파일을 만드는 것을 흉내 낸다. 훅이 허용하면 실제로 파일을 쓴다."""
        text = self.work_text(work_id, claims, status, extra)
        path = self.now / f"{work_id}.md"
        code, err = self.hook(session, "Write", {"file_path": str(path), "content": text})
        if code == 0:
            path.write_text(text, "utf-8")
        return code, err

    def test_project_without_harness_is_ignored(self):
        other = Path(tempfile.mkdtemp())
        try:
            code, _ = self.hook("A", "Edit", {"file_path": str(other / "a.txt")}, cwd=other)
            self.assertEqual(code, 0)
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_edit_without_work_file_is_denied(self):
        code, err = self.edit("A", "client/a.cs")
        self.assertEqual(code, 2)
        self.assertIn("자신의 작업 파일이 필요하다", err)

    def test_edit_inside_own_claim_is_allowed(self):
        self.assertEqual(self.start_work("A", "1005-1420-lobby", "client/UI/Lobby/, data/stages.json")[0], 0)
        self.assertEqual(self.edit("A", "client/UI/Lobby/Button.prefab")[0], 0)
        self.assertEqual(self.edit("A", "data/stages.json")[0], 0)
        self.assertEqual(self.edit("A", "CLIENT\\UI\\lobby\\x.cs")[0], 0)

    def test_edit_outside_own_claim_is_allowed_when_nobody_holds_it(self):
        self.start_work("A", "1005-1420-lobby", "client/UI/Lobby/")
        self.assertEqual(self.edit("A", "client/UI/Shop/Button.prefab")[0], 0)

    def test_claim_matches_whole_path_segments_only(self):
        self.start_work("A", "1005-1420-lobby", "client/UI/Lobby/")
        self.start_work("B", "1005-1435-data", "data/")
        self.assertEqual(self.edit("B", "client/UI/LobbyExtra/x.cs")[0], 0)
        self.assertEqual(self.edit("B", "client/UI/Lobby/x.cs")[0], 2)

    def test_edit_inside_other_claim_is_denied(self):
        self.start_work("A", "1005-1420-lobby", "client/UI/Lobby/")
        self.start_work("B", "1005-1435-data", "data/")
        code, err = self.edit("B", "client/UI/Lobby/Button.prefab")
        self.assertEqual(code, 2)
        self.assertIn("1005-1420-lobby", err)
        self.assertIn("잡고 있는 곳", err)

    def test_declaring_overlapping_claim_is_denied(self):
        self.start_work("A", "1005-1420-lobby", "client/UI/Lobby/")
        for claims in ("client/UI/", "client/UI/Lobby/Button.prefab", "."):
            code, err = self.start_work("B", "1005-1435-ui", claims)
            self.assertEqual(code, 2, claims)
            self.assertIn("겹친다", err)
        self.assertFalse((self.now / "1005-1435-ui.md").exists())
        self.assertEqual(self.start_work("B", "1005-1435-ui", "client/UI/Shop/")[0], 0)

    def test_overlap_allowed_after_user_approval(self):
        self.start_work("A", "1005-1420-lobby", "client/UI/")
        code, _ = self.start_work("B", "1005-1435-ui", "client/UI/Lobby/", extra="- 겹침 허용: 1005-1420-lobby")
        self.assertEqual(code, 0)
        self.assertEqual(self.edit("B", "client/UI/Lobby/x.cs")[0], 0)
        self.assertEqual(self.edit("B", "client/UI/Shop/x.cs")[0], 0)

    def test_other_sessions_in_progress_work_file_is_protected(self):
        self.start_work("A", "1005-1420-lobby", "client/UI/Lobby/")
        code, err = self.edit("B", ".game-harness/work/now/1005-1420-lobby.md")
        self.assertEqual(code, 2)
        self.assertIn("다른 세션이 진행 중", err)
        self.assertIn(".local/owners/1005-1420-lobby", err)

    def test_paused_work_can_be_taken_over(self):
        self.start_work("A", "1005-1420-lobby", "client/UI/Lobby/", status="멈춤")
        self.assertEqual(self.edit("B", "client/UI/Lobby/x.cs")[0], 2)
        self.assertEqual(self.edit("B", ".game-harness/work/now/1005-1420-lobby.md")[0], 0)
        self.assertEqual(self.edit("B", "client/UI/Lobby/x.cs")[0], 0)
        self.assertEqual(self.edit("A", "client/UI/Lobby/x.cs")[0], 2)

    def test_work_from_another_pc_blocks_until_taken_over(self):
        (self.now / "1004-2200-sound.md").write_text(self.work_text("1004-2200-sound", "client/Audio/"), "utf-8")
        code, err = self.edit("A", "client/Audio/a.wav.meta")
        self.assertEqual(code, 2)
        self.assertIn("1004-2200-sound", err)
        self.assertEqual(self.edit("A", ".game-harness/work/now/1004-2200-sound.md")[0], 0)
        self.assertEqual(self.edit("A", "client/Audio/a.wav.meta")[0], 0)

    def test_session_end_releases_ownership(self):
        self.start_work("A", "1005-1420-lobby", "client/UI/Lobby/")
        self.assertEqual(self.edit("B", ".game-harness/work/now/1005-1420-lobby.md")[0], 2)
        self.assertEqual(self.hook("A", "", {}, event="SessionEnd")[0], 0)
        self.assertEqual(self.edit("B", ".game-harness/work/now/1005-1420-lobby.md")[0], 0)

    def test_finished_work_does_not_block(self):
        self.start_work("A", "1005-1420-lobby", "client/UI/Lobby/", status="끝남")
        self.assertEqual(self.start_work("B", "1005-1435-ui", "client/UI/")[0], 0)
        self.assertEqual(self.edit("B", "client/UI/Lobby/x.cs")[0], 0)

    def test_harness_settings_and_archive_are_not_guarded(self):
        self.assertEqual(self.edit("A", ".game-harness/project.yaml")[0], 0)
        self.assertEqual(self.edit("A", ".game-harness/overrides/atlas.md")[0], 0)
        self.assertEqual(self.edit("A", ".game-harness/work/done/2026-10/05/1005-1420-lobby.md")[0], 0)

    def test_file_outside_project_is_ignored(self):
        outside = Path(tempfile.gettempdir()) / "game-harness-guard-outside.txt"
        self.assertEqual(self.hook("A", "Write", {"file_path": str(outside), "content": "x"})[0], 0)

    def test_codex_apply_patch_paths_are_checked(self):
        self.start_work("A", "1005-1420-lobby", "client/UI/Lobby/")
        self.start_work("B", "1005-1435-shop", "client/UI/Shop/")
        patch = "*** Begin Patch\n*** Update File: client/UI/Lobby/a.cs\n@@\n-a\n+b\n*** End Patch\n"
        self.assertEqual(self.hook("A", "apply_patch", {"command": patch})[0], 0)
        patch = "*** Begin Patch\n*** Add File: client/UI/Shop/b.cs\n+x\n*** End Patch\n"
        code, err = self.hook("A", "apply_patch", {"command": patch})
        self.assertEqual(code, 2)
        self.assertIn("client/UI/Shop/b.cs", err)

    def test_broken_input_does_not_block(self):
        result = subprocess.run([sys.executable, str(GUARD)], input=b"not json", capture_output=True)
        self.assertEqual(result.returncode, 0)


class LockTest(unittest.TestCase):
    def setUp(self):
        # with_lock.py는 자기 위치에서 프로젝트를 찾으므로 프로젝트 안의 자리에 복사해 쓴다.
        self.root = Path(tempfile.mkdtemp())
        tools = self.root / ".game-harness" / "harness" / "core" / "tools"
        tools.mkdir(parents=True)
        self.lock = tools / "with_lock.py"
        shutil.copyfile(LOCK, self.lock)
        self.locks = self.root / ".game-harness" / "work" / ".local" / "locks"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_lock(self, *args):
        return subprocess.run([sys.executable, str(self.lock), *args], capture_output=True)

    def test_runs_command_and_returns_its_exit_code(self):
        result = self.run_lock("editor", "--", sys.executable, "-c", "import sys; sys.exit(7)")
        self.assertEqual(result.returncode, 7)
        self.assertFalse((self.locks / "editor.lock").exists())

    def test_waits_for_running_holder_then_gives_up(self):
        holder = subprocess.Popen([sys.executable, str(self.lock), "editor", "--",
                                   sys.executable, "-c", "import time; time.sleep(6)"])
        try:
            for _ in range(50):
                if (self.locks / "editor.lock").exists():
                    break
                import time
                time.sleep(0.1)
            result = self.run_lock("editor", "--wait", "1", "--", sys.executable, "-c", "print('ran')")
            self.assertEqual(result.returncode, 75)
            self.assertNotIn(b"ran", result.stdout)
            other = self.run_lock("build", "--wait", "1", "--", sys.executable, "-c", "print('ran')")
            self.assertEqual(other.returncode, 0)
        finally:
            holder.wait()
        self.assertEqual(self.run_lock("editor", "--wait", "1", "--", sys.executable, "-c", "pass").returncode, 0)

    def test_stale_lock_from_dead_process_is_cleared(self):
        self.locks.mkdir(parents=True)
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        (self.locks / "editor.lock").write_text(json.dumps({"pid": dead.pid, "command": "x"}), "utf-8")
        result = self.run_lock("editor", "--wait", "1", "--", sys.executable, "-c", "pass")
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
