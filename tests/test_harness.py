"""harness.py를 임시 게임 프로젝트에 실제로 실행해 보는 시험."""
import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "game-harness"

spec = importlib.util.spec_from_file_location("harness", PLUGIN / "scripts" / "harness.py")
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class HarnessTest(unittest.TestCase):
    def setUp(self):
        # 시험이 원본 payload를 건드리지 않도록 플러그인을 임시 폴더로 복사해 쓴다.
        self.tmp = Path(tempfile.mkdtemp())
        self.plugin = self.tmp / "plugin"
        shutil.copytree(PLUGIN, self.plugin, ignore=shutil.ignore_patterns("__pycache__"))
        self.project = self.tmp / "game"
        self.project.mkdir()
        self._saved = (harness.PLUGIN_ROOT, harness.PAYLOAD)
        harness.PLUGIN_ROOT = self.plugin
        harness.PAYLOAD = self.plugin / "payload"

    def tearDown(self):
        harness.PLUGIN_ROOT, harness.PAYLOAD = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args):
        out = io.StringIO()
        # main()이 표준 출력의 인코딩을 바꾸려 하므로 reconfigure가 있는 진짜 스트림을 흉내 낸다.
        out.reconfigure = lambda **_: None
        err = io.StringIO()
        err.reconfigure = lambda **_: None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = harness.main([*args, "--project", str(self.project)])
        return code, out.getvalue() + err.getvalue()

    def manifest(self):
        return json.loads((self.project / ".game-harness" / "manifest.json").read_text("utf-8"))

    def release(self, version, extra_file=None):
        """임시 플러그인을 새 버전으로 만든다."""
        for path in (self.plugin / "plugin.json", self.plugin / ".claude-plugin" / "plugin.json"):
            data = json.loads(path.read_text("utf-8"))
            data["version"] = version
            path.write_text(json.dumps(data), "utf-8")
        changelog = self.plugin / "payload" / "CHANGELOG.md"
        text = changelog.read_text("utf-8")
        head, rest = text.split("\n## ", 1)
        changelog.write_text(
            f"{head}\n## {version} - 2099-01-01\n\n- 시험용 변경 {version}\n\n## {rest}", "utf-8"
        )
        workflow = self.plugin / "payload" / "core" / "workflow.md"
        workflow.write_text(workflow.read_text("utf-8") + f"\n{version}에서 추가한 줄.\n", "utf-8")
        if extra_file:
            (self.plugin / "payload" / "core" / extra_file).write_text("새 파일\n", "utf-8")

    def test_apply_creates_expected_files(self):
        code, out = self.run_cli("apply", "--modules", "unity")
        self.assertEqual(code, 0, out)
        root = self.project / ".game-harness"
        self.assertTrue((root / "harness" / "core" / "workflow.md").is_file())
        self.assertTrue((root / "harness" / "modules" / "unity" / "README.md").is_file())
        self.assertTrue((root / "harness" / "CHANGELOG.md").is_file())
        self.assertTrue((root / "project.yaml").is_file())
        self.assertTrue((root / "overrides" / "README.md").is_file())
        self.assertEqual((self.project / "CLAUDE.md").read_text("utf-8").strip(), "@AGENTS.md")
        agents = (self.project / "AGENTS.md").read_text("utf-8")
        self.assertIn("game-harness:begin", agents)
        self.assertIn("modules/unity/README.md", agents)
        manifest = self.manifest()
        self.assertEqual(manifest["modules"], ["unity"])
        self.assertEqual(manifest["harnessVersion"], harness.plugin_version())
        self.assertFalse((root / "harness.new").exists())

    def test_apply_without_modules_copies_core_only(self):
        self.run_cli("apply")
        self.assertFalse((self.project / ".game-harness" / "harness" / "modules").exists())
        self.assertEqual(self.manifest()["modules"], [])

    def test_apply_rejects_unknown_module(self):
        code, out = self.run_cli("apply", "--modules", "nope")
        self.assertEqual(code, 1)
        self.assertIn("없는 기능", out)
        self.assertFalse((self.project / ".game-harness" / "manifest.json").exists())

    def test_apply_preserves_existing_project_files(self):
        (self.project / "AGENTS.md").write_text("# 내 게임\n\n기존 규칙.\n", "utf-8")
        (self.project / "CLAUDE.md").write_text("내 클로드 설정\n", "utf-8")
        code, out = self.run_cli("apply")
        self.assertEqual(code, 0, out)
        agents = (self.project / "AGENTS.md").read_text("utf-8")
        self.assertTrue(agents.startswith("# 내 게임\n\n기존 규칙.\n"))
        self.assertIn("game-harness:begin", agents)
        self.assertEqual((self.project / "CLAUDE.md").read_text("utf-8"), "내 클로드 설정\n")
        self.assertIn("@AGENTS.md", out)

    def test_apply_twice_changes_nothing(self):
        self.run_cli("apply", "--modules", "unity")
        (self.project / ".game-harness" / "project.yaml").write_text("game:\n  name: 공룡\n", "utf-8")
        before = self.manifest()
        agents_before = (self.project / "AGENTS.md").read_text("utf-8")
        code, out = self.run_cli("apply")
        self.assertEqual(code, 0)
        self.assertIn("이미", out)
        self.assertEqual(self.manifest(), before)
        self.assertEqual((self.project / "AGENTS.md").read_text("utf-8"), agents_before)
        self.assertIn("공룡", (self.project / ".game-harness" / "project.yaml").read_text("utf-8"))

    def test_update_without_changes_is_noop(self):
        self.run_cli("apply")
        code, out = self.run_cli("update", "--yes")
        self.assertEqual(code, 0)
        self.assertIn("이미 최신", out)
        self.assertEqual(len(self.manifest()["history"]), 1)

    def test_diff_reports_version_changelog_and_files(self):
        self.run_cli("apply")
        (self.plugin / "payload" / "core" / "cleanup.md").unlink()
        self.release("0.2.0", extra_file="new-rule.md")
        code, out = self.run_cli("diff", "--json")
        self.assertEqual(code, 0, out)
        diff = json.loads(out)
        self.assertEqual(diff["direction"], "upgrade")
        self.assertEqual(diff["availableVersion"], "0.2.0")
        self.assertEqual(diff["added"], ["core/new-rule.md"])
        self.assertEqual(diff["removed"], ["core/cleanup.md"])
        self.assertIn("core/workflow.md", diff["changed"])
        self.assertIn("CHANGELOG.md", diff["changed"])
        self.assertEqual([s["version"] for s in diff["changelog"]], ["0.2.0"])
        self.assertIn("시험용 변경 0.2.0", diff["changelog"][0]["body"])

    def test_update_requires_confirmation(self):
        self.run_cli("apply")
        self.release("0.2.0")
        before = self.manifest()
        code, out = self.run_cli("update")
        self.assertEqual(code, 2)
        self.assertIn("아무것도 바꾸지 않았다", out)
        self.assertIn("시험용 변경 0.2.0", out)
        self.assertEqual(self.manifest(), before)

    def test_update_replaces_harness_and_keeps_project_files(self):
        (self.project / "AGENTS.md").write_text("# 내 게임\n\n기존 규칙.\n", "utf-8")
        self.run_cli("apply", "--modules", "unity")
        root = self.project / ".game-harness"
        (root / "project.yaml").write_text("game:\n  name: 공룡\n", "utf-8")
        (root / "overrides" / "atlas.md").write_text("아틀라스 규칙\n", "utf-8")
        (self.plugin / "payload" / "core" / "cleanup.md").unlink()
        self.release("0.2.0", extra_file="new-rule.md")

        code, out = self.run_cli("update", "--yes")
        self.assertEqual(code, 0, out)
        self.assertTrue((root / "harness" / "core" / "new-rule.md").is_file())
        self.assertFalse((root / "harness" / "core" / "cleanup.md").exists())
        self.assertIn("0.2.0에서 추가한 줄", (root / "harness" / "core" / "workflow.md").read_text("utf-8"))
        self.assertEqual((root / "project.yaml").read_text("utf-8"), "game:\n  name: 공룡\n")
        self.assertEqual((root / "overrides" / "atlas.md").read_text("utf-8"), "아틀라스 규칙\n")
        agents = (self.project / "AGENTS.md").read_text("utf-8")
        self.assertTrue(agents.startswith("# 내 게임\n\n기존 규칙.\n"))
        self.assertEqual(agents.count("game-harness:begin"), 1)
        self.assertIn("0.2.0", agents)
        manifest = self.manifest()
        self.assertEqual(manifest["harnessVersion"], "0.2.0")
        self.assertEqual(manifest["modules"], ["unity"])
        self.assertEqual([h["to"] for h in manifest["history"]], ["0.1.0", "0.2.0"])
        self.assertEqual(json.loads(self.run_cli("diff", "--json")[1])["changed"], [])

    def test_local_edits_are_reported_and_overwritten(self):
        self.run_cli("apply")
        harness_dir = self.project / ".game-harness" / "harness"
        (harness_dir / "core" / "workflow.md").write_text("손으로 고침\n", "utf-8")
        (harness_dir / "core" / "cleanup.md").unlink()
        (harness_dir / "core" / "stray.md").write_text("끼어든 파일\n", "utf-8")
        diff = json.loads(self.run_cli("diff", "--json")[1])
        self.assertEqual(diff["direction"], "same")
        self.assertEqual(diff["locallyModified"], ["core/workflow.md"])
        self.assertEqual(diff["missing"], ["core/cleanup.md"])
        self.assertEqual(diff["untracked"], ["core/stray.md"])

        self.assertEqual(self.run_cli("update")[0], 2)
        self.assertEqual(self.run_cli("update", "--yes")[0], 0)
        self.assertNotEqual((harness_dir / "core" / "workflow.md").read_text("utf-8"), "손으로 고침\n")
        self.assertTrue((harness_dir / "core" / "cleanup.md").is_file())
        self.assertFalse((harness_dir / "core" / "stray.md").exists())

    def test_line_ending_change_is_not_a_modification(self):
        self.run_cli("apply")
        path = self.project / ".game-harness" / "harness" / "core" / "workflow.md"
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        diff = json.loads(self.run_cli("diff", "--json")[1])
        self.assertEqual(diff["locallyModified"], [])

    def test_update_can_change_modules(self):
        self.run_cli("apply")
        diff = json.loads(self.run_cli("diff", "--modules", "unity", "--json")[1])
        self.assertIn("modules/unity/README.md", diff["added"])
        self.assertEqual(self.run_cli("update", "--modules", "unity", "--yes")[0], 0)
        self.assertEqual(self.manifest()["modules"], ["unity"])
        self.assertIn("modules/unity/README.md", (self.project / "AGENTS.md").read_text("utf-8"))

    def test_status_before_apply(self):
        code, out = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("적용되어 있지 않다", out)
        self.assertIn("unity", out)

    def test_update_before_apply_fails(self):
        code, out = self.run_cli("update", "--yes")
        self.assertEqual(code, 1)
        self.assertIn("적용되어 있지 않다", out)


class ReleaseCheckTest(unittest.TestCase):
    def test_repository_is_releasable(self):
        """실제 저장소의 두 설정 파일 버전과 CHANGELOG 최신 항목이 일치하는지 본다."""
        out = io.StringIO()
        out.reconfigure = lambda **_: None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = harness.main(["check"])
        self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    sys.exit(unittest.main())
