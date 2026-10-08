"""Exercise global lifecycle operations against isolated home/project directories."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "game-harness"
spec = importlib.util.spec_from_file_location("global_runtime_test", PLUGIN / "scripts" / "global_runtime.py")
runtime_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime_module)


class GlobalRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.plugin = self.root / "plugin"
        self.plugin.mkdir()
        self.project = self.root / "game"
        self.project.mkdir()
        self.environment = patch.dict(os.environ, {"GAME_HARNESS_HOME": str(self.home),
                                                  "CODEX_HOME": str(self.home / ".codex")})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        (self.plugin / "plugin.json").write_text(json.dumps({"name": "game-harness", "version": "0.2.0"}))
        (self.plugin / "scripts").mkdir()
        for name in (*runtime_module.RUNTIME_FILES, "hook_entry.mjs"):
            shutil.copyfile(PLUGIN / "scripts" / name, self.plugin / "scripts" / name)
        for name in ("alpha", "beta"):
            folder = self.plugin / "bundled" / "skills" / name
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Test {name}\n---\n\nBase {name}\n")
            (folder / "reference.md").write_text(f"Reference for {name}\n")
        agents = self.plugin / "bundled" / "agents"
        agents.mkdir()
        (agents / "reviewer.md").write_text("---\nname: reviewer\ndescription: Review the result\ntools: Read, Bash\n---\n\nRead and report.\n")
        self.runtime = runtime_module.Runtime(self.home, self.plugin)

    def sync(self):
        return self.runtime.sync()

    def skill(self, name="alpha"):
        return self.home / ".agents" / "skills" / name

    def guard(self, tool, tool_input, session="", cwd=None):
        payload = {"tool_name": tool, "tool_input": tool_input, "session_id": session,
                   "cwd": str(cwd or self.project), "hook_event_name": "PreToolUse"}
        return subprocess.run([sys.executable, str(self.plugin / "scripts" / "work_guard.py")],
                              input=json.dumps(payload).encode(), capture_output=True)

    def test_install_registers_common_skills_and_both_agent_formats(self):
        result = self.sync()
        self.assertEqual(result["version"], "0.2.0")
        self.assertTrue((self.skill() / "SKILL.md").is_file())
        wrapper = (self.home / ".claude/skills/alpha/SKILL.md").read_text()
        self.assertIn((self.skill() / "SKILL.md").as_posix(), wrapper)
        self.assertTrue((self.home / ".claude/agents/reviewer.md").is_file())
        import tomllib
        agent = tomllib.loads((self.home / ".codex/agents/reviewer.toml").read_text())
        self.assertEqual(agent["name"], "reviewer")
        self.assertIn("Read and report.", agent["developer_instructions"])
        self.assertNotIn("model", agent)
        self.assertFalse((self.project / ".game-harness").exists())
        self.assertFalse(self.runtime.integrity()["missing"])

    def test_same_version_and_content_does_not_rewrite_installation(self):
        self.sync()
        before = self.runtime.manifest_path.read_bytes()
        timestamp = (self.skill() / "SKILL.md").stat().st_mtime_ns
        result = self.sync()
        self.assertEqual(result["changed"], [])
        self.assertEqual(self.runtime.manifest_path.read_bytes(), before)
        self.assertEqual((self.skill() / "SKILL.md").stat().st_mtime_ns, timestamp)

    def test_unowned_collision_aborts_before_overwriting_anything(self):
        self.skill().mkdir(parents=True)
        path = self.skill() / "SKILL.md"
        path.write_text("someone else's skill")
        with self.assertRaisesRegex(runtime_module.RuntimeError, "Unowned"):
            self.sync()
        self.assertEqual(path.read_text(), "someone else's skill")
        self.assertFalse(self.skill("beta").exists())
        self.assertFalse(self.runtime.manifest_path.exists())

    def test_update_adds_removes_and_keeps_unrelated_global_and_local_files(self):
        self.sync()
        result = self.runtime.prepare("skill", "alpha", self.project)
        override = Path(result["override"])
        override.write_text(override.read_text("utf-8") + "\n- Use 8 frames.\n", "utf-8")
        original = override.read_bytes()
        unrelated = self.skill("unity-cli")
        unrelated.mkdir()
        (unrelated / "SKILL.md").write_text("Unity official skill")
        source = self.plugin / "bundled/skills"
        shutil.rmtree(source / "beta")
        (source / "alpha/SKILL.md").write_text("---\nname: alpha\ndescription: Test alpha\n---\n\nNew base\n")
        (source / "gamma").mkdir()
        (source / "gamma/SKILL.md").write_text("---\nname: gamma\ndescription: New skill\n---\n\nNew\n")
        (self.plugin / "plugin.json").write_text(json.dumps({"name": "game-harness", "version": "0.3.0"}))
        update = self.sync()
        self.assertIn("skills/beta", update["removed"])
        self.assertTrue(self.skill("gamma").is_dir())
        self.assertFalse(self.skill("beta").exists())
        self.assertEqual((unrelated / "SKILL.md").read_text(), "Unity official skill")
        self.assertEqual(override.read_bytes(), original)
        prepared = self.runtime.prepare("skill", "alpha", self.project)
        self.assertTrue(prepared["active"])
        self.assertTrue(prepared["warnings"])

    def test_integrity_reports_missing_modified_extra_and_repair_restores(self):
        self.sync()
        (self.skill() / "SKILL.md").write_text("tampered")
        (self.skill() / "reference.md").unlink()
        (self.skill() / "extra.txt").write_text("untracked")
        status = self.runtime.integrity()
        self.assertIn("skills/alpha/SKILL.md", status["modified"])
        self.assertIn("skills/alpha/reference.md", status["missing"])
        self.assertIn("skills/alpha/extra.txt", status["untracked"])
        with self.assertRaisesRegex(runtime_module.RuntimeError, "damaged"):
            self.runtime.prepare("skill", "alpha", self.project)
        self.runtime.sync(repair=True)
        clean = self.runtime.integrity()
        self.assertEqual([clean[key] for key in ("missing", "modified", "untracked")], [[], [], []])

    def test_failed_staging_leaves_old_files_and_manifest(self):
        self.sync()
        before = self.runtime.manifest_path.read_bytes()
        original = (self.skill() / "SKILL.md").read_bytes()
        (self.plugin / "bundled/skills/alpha/reference.md").write_text("new")
        actual_write = Path.write_bytes
        def fail_staged(path, data):
            if path.name == "reference.md" and "new" in path.parts:
                raise OSError("staging failure")
            return actual_write(path, data)
        with patch.object(Path, "write_bytes", fail_staged):
            with self.assertRaisesRegex(OSError, "staging failure"):
                self.sync()
        self.assertEqual(self.runtime.manifest_path.read_bytes(), before)
        self.assertEqual((self.skill() / "SKILL.md").read_bytes(), original)

    def test_failed_commit_rolls_back_all_swapped_units(self):
        self.sync()
        before = self.runtime.manifest_path.read_bytes()
        original = (self.skill() / "SKILL.md").read_bytes()
        (self.plugin / "bundled/skills/alpha/reference.md").write_text("new")
        with patch.object(runtime_module.os, "replace", side_effect=OSError("commit failure")):
            with self.assertRaisesRegex(OSError, "commit failure"):
                self.sync()
        self.assertEqual(self.runtime.manifest_path.read_bytes(), before)
        self.assertEqual((self.skill() / "SKILL.md").read_bytes(), original)
        self.assertEqual(self.runtime.integrity()["modified"], [])
        self.assertFalse(list(self.home.rglob(".game-harness-txn-*")))

    def test_prepare_creates_only_used_template_and_preserves_existing_content(self):
        self.sync()
        result = self.runtime.prepare("skill", "alpha", self.project)
        self.assertTrue(result["created"])
        self.assertFalse(result["active"])
        override = Path(result["override"])
        self.assertFalse((override.parents[1] / "beta").exists())
        override.write_text("# Local\n\n- Use 8 frames.\n", "utf-8")
        prepared = self.runtime.prepare("skill", "alpha", self.project)
        self.assertFalse(prepared["created"])
        self.assertTrue(prepared["active"])
        self.assertEqual(prepared["instructions"], "# Local\n\n- Use 8 frames.\n")

    def test_prepare_from_subdirectory_uses_project_root_and_agent_has_own_override(self):
        self.sync()
        (self.project / ".game-harness").mkdir()
        nested = self.project / "Assets/Characters"
        nested.mkdir(parents=True)
        skill = self.runtime.prepare("skill", "alpha", nested)
        agent = self.runtime.prepare("agent", "reviewer", nested)
        self.assertEqual(skill["project"], str(self.project.resolve()))
        self.assertEqual(agent["project"], skill["project"])
        self.assertIn("agents", Path(agent["override"]).parts)
        self.assertNotEqual(skill["override"], agent["override"])

    def test_prepare_rejects_unknown_or_traversing_names(self):
        self.sync()
        for name in ("unknown", "../alpha", "/alpha"):
            with self.assertRaises(runtime_module.RuntimeError):
                self.runtime.prepare("skill", name, self.project)
        self.assertFalse((self.project / ".game-harness").exists())

    def test_override_for_removed_capability_is_preserved_and_reported(self):
        self.sync()
        old = self.runtime.prepare("skill", "beta", self.project)
        shutil.rmtree(self.plugin / "bundled/skills/beta")
        self.sync()
        result = self.runtime.prepare("skill", "alpha", self.project)
        self.assertTrue(Path(old["override"]).is_file())
        self.assertIn("No managed target", result["warnings"][0])

    def test_global_guard_denies_edit_delete_move_and_parent_delete_without_session(self):
        self.sync()
        file = str(self.skill() / "SKILL.md")
        for tool, data in (("Edit", {"file_path": file}), ("Delete", {"path": file}),
                           ("Move", {"source": file, "destination": str(self.project / "copy.md")}),
                           ("Delete", {"path": str(self.home / ".agents/skills")}),
                           ("Write", {"file_path": str(self.runtime.manifest_path)}),
                           ("Edit", {"file_path": str(self.plugin / "scripts/work_guard.py")})):
            result = self.guard(tool, data)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("override.md", result.stderr.decode("utf-8"))

    def test_patch_move_destination_and_delete_are_protected(self):
        self.sync()
        file = str(self.skill() / "SKILL.md")
        for text in (f"*** Delete File: {file}\n", f"*** Update File: local.md\n*** Move to: {file}\n"):
            result = self.guard("apply_patch", {"input": "*** Begin Patch\n" + text + "*** End Patch\n"})
            self.assertEqual(result.returncode, 2, result.stderr)

    def test_local_override_and_unrelated_global_file_are_allowed(self):
        self.sync()
        override = self.runtime.prepare("skill", "alpha", self.project)["override"]
        self.assertEqual(self.guard("Write", {"file_path": override}).returncode, 0)
        unrelated = self.skill("unity-cli") / "SKILL.md"
        self.assertEqual(self.guard("Write", {"file_path": str(unrelated)}).returncode, 0)

    def test_corrupt_manifest_fails_closed_for_global_protection(self):
        self.sync()
        self.runtime.manifest_path.write_text("not json")
        result = self.guard("Edit", {"file_path": str(self.skill() / "SKILL.md")})
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_manifest_cannot_redirect_deletions_outside_managed_units(self):
        self.sync()
        manifest = self.runtime.manifest()
        manifest["units"]["skills/../../other"] = {"files": {"": "x"}}
        self.runtime.manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(runtime_module.RuntimeError):
            self.sync()

    def test_concurrent_sync_processes_share_a_consistent_installation(self):
        args = [sys.executable, str(self.plugin / "scripts/global_runtime.py"), "sync"]
        processes = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        for process in processes:
            out, err = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, err)
            self.assertEqual(json.loads(out)["version"], "0.2.0")
        self.assertEqual(self.runtime.integrity()["modified"], [])
        self.assertFalse((self.runtime.state / "sync.lock").exists())

    def test_guard_follows_a_link_from_the_project_to_global_source(self):
        self.sync()
        alias = self.project / "alias"
        try:
            alias.symlink_to(self.skill(), target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("symlinks unavailable")
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(self.skill())],
                                    capture_output=True)
            if result.returncode:
                self.skipTest("directory links unavailable")
        self.addCleanup(alias.unlink if alias.is_symlink() else alias.rmdir)
        result = self.guard("Edit", {"file_path": str(alias / "SKILL.md")})
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_linked_global_destination_is_rejected_without_touching_target(self):
        target = self.root / "unrelated"
        target.mkdir()
        (target / "keep.txt").write_text("keep")
        dest = self.skill()
        dest.parent.mkdir(parents=True)
        try:
            dest.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("symlinks unavailable")
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(dest), str(target)], capture_output=True)
            if result.returncode:
                self.skipTest("directory links unavailable")
        self.addCleanup(dest.unlink if dest.is_symlink() else dest.rmdir)
        with self.assertRaisesRegex(runtime_module.RuntimeError, "Linked"):
            self.sync()
        self.assertEqual((target / "keep.txt").read_text(), "keep")

    def test_stale_lock_reports_error_without_changing_installation(self):
        self.sync()
        (self.runtime.state / "sync.lock").write_text("stale")
        with patch.object(runtime_module.time, "monotonic", side_effect=[0, 11]):
            with self.assertRaisesRegex(runtime_module.RuntimeError, "stale lock"):
                self.sync()

    def test_session_start_sync_and_subagent_start_preparation(self):
        result = subprocess.run([sys.executable, str(self.plugin / "scripts/global_runtime.py"), "hook"],
            input=json.dumps({"hook_event_name": "SessionStart", "cwd": str(self.project)}).encode(),
            capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertFalse((self.project / ".game-harness").exists())
        result = subprocess.run([sys.executable, str(self.plugin / "scripts/global_runtime.py"), "hook"],
            input=json.dumps({"hook_event_name": "SubagentStart", "agent_type": "reviewer",
                              "cwd": str(self.project)}).encode(), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.project / ".game-harness/overrides/agents/reviewer/override.md").is_file())

    def test_installed_runtime_can_prepare_without_source_checkout(self):
        self.sync()
        result = subprocess.run([sys.executable, str(self.runtime.state / "global_runtime.py"),
                                 "prepare", "skill", "alpha", "--project", str(self.project)],
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["created"])

    @unittest.skipUnless(shutil.which("node"), "Node is not installed")
    def test_node_hook_launcher_runs_lifecycle_and_guard(self):
        result = subprocess.run(["node", str(self.plugin / "scripts/hook_entry.mjs"), "lifecycle"],
                                input=b'{"hook_event_name":"SessionStart"}', capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
                   "tool_input": {"file_path": str(self.skill() / "SKILL.md")}}
        result = subprocess.run(["node", str(self.plugin / "scripts/hook_entry.mjs"), "guard"],
                                input=json.dumps(payload).encode(), capture_output=True)
        self.assertEqual(result.returncode, 2, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node is not installed")
    def test_node_guard_blocks_when_the_python_guard_cannot_start(self):
        (self.plugin / "scripts/work_guard.py").write_text("raise RuntimeError('broken guard')\n")
        result = subprocess.run(["node", str(self.plugin / "scripts/hook_entry.mjs"), "guard"],
                                input=b'{}', capture_output=True)
        self.assertEqual(result.returncode, 2, result.stderr)


if __name__ == "__main__":
    unittest.main()
