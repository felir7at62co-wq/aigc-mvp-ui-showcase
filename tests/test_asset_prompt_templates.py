import tempfile
import unittest
from pathlib import Path


class AssetPromptTemplateTests(unittest.TestCase):
    def test_project_template_overrides_bundled_default(self):
        from core.asset_prompt_templates import (
            resolve_asset_prompt_template,
            save_project_asset_prompt_template,
        )

        with tempfile.TemporaryDirectory() as project_dir, tempfile.TemporaryDirectory() as app_dir:
            bundled = Path(app_dir, "prompts", "default_asset_prompt.txt")
            bundled.parent.mkdir(parents=True)
            bundled.write_text(
                "bundled asset template {screenplay_text} 别名 集数 生图提示词",
                encoding="utf-8",
            )

            saved = save_project_asset_prompt_template(
                project_dir,
                "character",
                "custom asset template {screenplay_text} 别名 集数 生图提示词",
            )
            resolved = resolve_asset_prompt_template(project_dir, "character", app_dir)

            self.assertEqual(Path(resolved), Path(saved))
            self.assertEqual(
                Path(resolved).read_text(encoding="utf-8"),
                "custom asset template {screenplay_text} 别名 集数 生图提示词",
            )

    def test_restoring_project_template_falls_back_to_bundled_default(self):
        from core.asset_prompt_templates import (
            remove_project_asset_prompt_template,
            resolve_asset_prompt_template,
            save_project_asset_prompt_template,
        )

        with tempfile.TemporaryDirectory() as project_dir, tempfile.TemporaryDirectory() as app_dir:
            bundled = Path(app_dir, "prompts", "default_asset_prompt.txt")
            bundled.parent.mkdir(parents=True)
            bundled.write_text(
                "bundled asset template {screenplay_text} 别名 集数 生图提示词",
                encoding="utf-8",
            )
            save_project_asset_prompt_template(
                project_dir,
                "scene",
                "custom asset template {screenplay_text} 别名 集数 生图提示词",
            )

            remove_project_asset_prompt_template(project_dir, "scene")

            self.assertEqual(
                Path(resolve_asset_prompt_template(project_dir, "scene", app_dir)),
                bundled,
            )

    def test_configured_template_is_used_when_project_has_no_override(self):
        from core.asset_prompt_templates import resolve_asset_prompt_template

        with tempfile.TemporaryDirectory() as project_dir, tempfile.TemporaryDirectory() as app_dir:
            configured = Path(app_dir, "team_asset_prompt.txt")
            configured.write_text(
                "team template {screenplay_text} 别名 集数 生图提示词",
                encoding="utf-8",
            )

            resolved = resolve_asset_prompt_template(
                project_dir, "character", app_dir, str(configured)
            )

            self.assertEqual(Path(resolved), configured)

    def test_default_asset_template_does_not_filter_scenes_by_occurrence_count(self):
        template = Path("prompts/default_asset_prompt.txt").read_text(encoding="utf-8")

        self.assertNotIn("仅保留出镜＞3次", template)
        self.assertIn("关键场景都必须保留", template)

    def test_default_asset_template_requires_four_column_contract(self):
        template = Path("prompts/default_asset_prompt.txt").read_text(encoding="utf-8")

        self.assertIn("名称、别名、出场集数和生图提示词", template)
        self.assertIn("角色中文名|别名1,别名2,代称|01,02,03|生图提示词", template)
        self.assertIn("场景中文名|场景别名1,场景别名2|01,03,05|生图提示词", template)
        self.assertIn("角色名_阶段名", template)

    def test_portable_runtime_requires_unified_asset_template(self):
        from core.packaged_runtime import _required_resources

        required = set(_required_resources())
        self.assertTrue(
            {
                "prompts/default_asset_prompt.txt",
                "prompts/default_asset_selector_prompt.txt",
            }.issubset(required)
        )

    def test_rejects_legacy_two_column_template(self):
        from core.asset_prompt_templates import save_project_asset_prompt_template

        with tempfile.TemporaryDirectory() as project_dir:
            with self.assertRaises(ValueError):
                save_project_asset_prompt_template(
                    project_dir,
                    "scene",
                    "场景中文名|中文描述 {screenplay_text}",
                )


if __name__ == "__main__":
    unittest.main()
