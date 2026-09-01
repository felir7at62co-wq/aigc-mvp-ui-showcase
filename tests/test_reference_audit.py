import tempfile
import unittest
from pathlib import Path


class DummyLLM:
    def generate(self, messages):
        return ""


class AssetStandardizationTests(unittest.TestCase):
    def test_asset_context_standardizes_records_and_filters_generic_aliases(self):
        from core.asset_context import build_asset_context

        with tempfile.TemporaryDirectory() as project_dir:
            assets = Path(project_dir, "assets")
            assets.mkdir()
            (assets / "character_prompts.txt").write_text(
                "孙大勇|勇哥,他,老板,大勇|01,02|前期衣衫破旧，后期深色西装，单张角色设定图，右侧三视图，纯白背景，禁止任何文字\n",
                encoding="utf-8",
            )

            context = build_asset_context(project_dir)
            record = context["assets"]["character"][0]

            self.assertEqual(record["name"], "孙大勇")
            self.assertNotIn("base_name", record)
            self.assertIn("勇哥", record["strong_aliases"])
            self.assertIn("大勇", record["strong_aliases"])
            self.assertNotIn("他", record["strong_aliases"])
            self.assertNotIn("老板", record["strong_aliases"])
            self.assertTrue(record["needs_phase_split"])
            self.assertEqual(record["asset_prompt"], record["prompt"])
            self.assertNotIn("三视图", record["visual_desc"])
            self.assertNotIn("纯白", record["visual_desc"])
            self.assertNotIn("禁止任何文字", record["visual_desc"])

    def test_prop_text_permission_defaults_to_false_unless_text_prop(self):
        from core.asset_context import build_asset_context

        with tempfile.TemporaryDirectory() as project_dir:
            assets = Path(project_dir, "assets")
            assets.mkdir()
            (assets / "prop_prompts.txt").write_text(
                "玉佩|吊坠|01|青绿色玉佩，无文字\n"
                "离婚协议|协议,文件|01|纸质协议，道具上允许文字\n",
                encoding="utf-8",
            )

            context = build_asset_context(project_dir)
            props = {r["name"]: r for r in context["assets"]["prop"]}

            self.assertFalse(props["玉佩"]["allows_text"])
            self.assertTrue(props["离婚协议"]["allows_text"])
            self.assertEqual(props["离婚协议"]["category"], "prop")


class PromptReferenceAuditTests(unittest.TestCase):
    def _generator(self):
        from agents.prompt_generator import PromptGenerator

        generator = PromptGenerator(DummyLLM())
        generator._character_guide = [
            {
                "name": "江蓁_前期",
                "aliases": ["蓁蓁", "江设计师"],
                "episodes": ["01", "02", "05"],
                "desc": "前期造型摘要",
            },
            {
                "name": "江蓁_后期",
                "aliases": ["蓁蓁"],
                "episodes": ["21", "40"],
                "desc": "后期造型摘要",
            },
            {
                "name": "许明磊_前期",
                "aliases": ["许总"],
                "episodes": ["05"],
                "desc": "西装，冷峻",
            },
        ]
        generator._scene_guide = [
            {
                "name": "许家客厅",
                "aliases": ["客厅", "许家大厅"],
                "episodes": ["05"],
                "desc": "许家豪宅客厅",
            },
            {
                "name": "设计公司办公室",
                "aliases": ["公司"],
                "episodes": ["01"],
                "desc": "现代办公室",
            },
        ]
        generator._prop_guide = [
            {
                "name": "离婚协议",
                "aliases": ["协议", "文件"],
                "episodes": ["05"],
                "allows_text": True,
                "desc": "纸质协议",
            }
        ]
        return generator

    def test_roster_text_contains_episode_asset_whitelist(self):
        roster = self._generator()._build_roster_text(5)

        self.assertIn("【第05集可用角色】", roster)
        self.assertIn("正式名：江蓁_前期", roster)
        self.assertNotIn("江蓁_后期 |", roster)
        self.assertIn("【第05集可用场景】", roster)
        self.assertIn("正式名：许家客厅", roster)
        self.assertIn("【第05集可用道具】", roster)
        self.assertIn("正式名：离婚协议", roster)
        self.assertIn("禁止输出基础名", roster)
        self.assertIn("别名只帮助理解", roster)

    def test_reference_audit_auto_fixes_alias_scene_and_prop_alias(self):
        generator = self._generator()
        script = (
            "镜头1：\n"
            "出镜人物【蓁蓁、许总】\n"
            "核心场景：客厅\n"
            "关键道具【协议】\n"
            "画面描述：【真人短剧写实风格 + 近景 + 客厅 + 蓁蓁看向许总】\n"
        )

        fixed, issues = generator._audit_and_fix_references(script, 5)

        self.assertIn("出镜人物【江蓁_前期、许明磊_前期】", fixed)
        self.assertIn("核心场景：许家客厅", fixed)
        self.assertIn("关键道具【离婚协议】", fixed)
        self.assertFalse(issues)

    def test_reference_audit_flags_wrong_phase_and_unknown_scene(self):
        generator = self._generator()
        script = (
            "镜头1：\n"
            "出镜人物【江蓁_后期】\n"
            "核心场景：陌生房间\n"
            "关键道具【无】\n"
            "画面描述：【真人短剧写实风格 + 中景 + 陌生房间】\n"
        )

        _fixed, issues = generator._audit_and_fix_references(script, 5)

        joined = "\n".join(issues)
        self.assertIn("江蓁_后期", joined)
        self.assertIn("不在第05集角色白名单", joined)
        self.assertIn("陌生房间", joined)
        self.assertIn("不在第05集场景白名单", joined)

    def test_reference_audit_flags_missing_required_fields(self):
        generator = self._generator()
        script = "镜头1：\n出镜人物【江蓁_前期】\n核心场景：许家客厅\n画面描述：【近景】\n"

        _fixed, issues = generator._audit_and_fix_references(script, 5)

        self.assertIn("镜头1 缺少: 关键道具", "\n".join(issues))


if __name__ == "__main__":
    unittest.main()
