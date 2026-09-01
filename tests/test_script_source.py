import json
import os
import tempfile
import unittest

from core.project import Project
from core.script_source import ProjectScriptSource


class ProjectScriptSourceTests(unittest.TestCase):
    def test_project_copies_source_and_keeps_visual_segments_unfiltered(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, "screenplay.txt")
            with open(source_path, "w", encoding="utf-8") as handle:
                handle.write("第1集\n版本二：林夏走进房间。\n【下集钩子】她看见一封信。\n第2集\n第二集正文。")
            project = Project.create(os.path.join(directory, "projects"), "demo", source_path)
            source = ProjectScriptSource(project.project_dir)

            self.assertNotEqual(os.path.abspath(source_path), project.state.script_path)
            self.assertTrue(project.state.script_path.startswith(os.path.join(project.project_dir, "source")))
            self.assertIn("版本二", source.full_text())
            self.assertIn("下集钩子", source.segment("01").text)
            self.assertTrue(os.path.isfile(os.path.join(source.visual_episodes_dir(), "02.txt")))
            self.assertEqual(project.manifest.data["project"]["source_sha256"], source.source_hash())
            with open(source.segments_path, "r", encoding="utf-8") as handle:
                self.assertEqual(len(json.load(handle)["segments"]), 2)

    def test_legacy_project_builds_canonical_source_on_load(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, "legacy.txt")
            with open(source_path, "w", encoding="utf-8") as handle:
                handle.write("没有分集标记的正文")
            project = Project.create(os.path.join(directory, "projects"), "legacy", source_path)
            os.remove(ProjectScriptSource(project.project_dir).normalized_path)
            loaded = Project.load(project.project_dir)
            self.assertTrue(os.path.isfile(ProjectScriptSource(loaded.project_dir).normalized_path))

    def test_loading_existing_project_with_new_script_replaces_source(self):
        with tempfile.TemporaryDirectory() as directory:
            first_path = os.path.join(directory, "first.txt")
            second_path = os.path.join(directory, "second.txt")
            with open(first_path, "w", encoding="utf-8") as handle:
                handle.write("第1集\n旧剧本")
            with open(second_path, "w", encoding="utf-8") as handle:
                handle.write("第1集\n新剧本")
            project = Project.create(os.path.join(directory, "projects"), "demo", first_path)
            project.set_artifact("01", "asset", "completed", input_hash="old-source")
            loaded = Project.load(project.project_dir, second_path)
            self.assertIn("新剧本", ProjectScriptSource(loaded.project_dir).full_text())
            self.assertNotIn("旧剧本", ProjectScriptSource(loaded.project_dir).full_text())
            self.assertEqual(loaded.get_step_status("prompt"), "pending")
            self.assertEqual(loaded.manifest.get("01", "asset").status, "stale")


if __name__ == "__main__":
    unittest.main()
