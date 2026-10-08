"""game-harness 제작 스킬 묶음의 구성이 어긋나지 않았는지 확인하는 시험."""
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "game-harness"
SKILLS = PLUGIN / "bundled" / "skills"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


class GameSkillsTest(unittest.TestCase):
    def test_every_skill_is_named_after_its_folder(self):
        folders = [p for p in SKILLS.iterdir() if p.is_dir()]
        self.assertTrue(folders)
        for folder in folders:
            match = re.search(r"^name:\s*(.+)$", text(folder / "SKILL.md"), re.MULTILINE)
            self.assertIsNotNone(match, folder.name)
            self.assertEqual(match.group(1).strip().strip("\"'"), folder.name)

    def test_reviewer_agent_matches_the_copy_in_the_skill(self):
        name = "2d-rig-reviewer.md"
        self.assertEqual(text(PLUGIN / "bundled" / "agents" / name),
                         text(SKILLS / "2d-character-animation" / "reviewer" / name))

    def test_both_manifests_have_the_same_version(self):
        claude = json.loads(text(PLUGIN / ".claude-plugin" / "plugin.json"))
        codex = json.loads(text(PLUGIN / "plugin.json"))
        self.assertEqual(claude["version"], codex["version"])

    def test_no_path_into_one_users_home(self):
        found = [str(p.relative_to(PLUGIN)) for p in (PLUGIN / "bundled").rglob("*")
                 if p.is_file() and p.suffix not in (".png", ".pyc") and re.search(r"Users[\\/]+Admin", text(p))]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
