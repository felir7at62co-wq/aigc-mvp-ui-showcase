import os
import tempfile
import unittest
from unittest.mock import patch

from core.batch_shot_import import BatchShotImporter
from core.project import Project


SHOT_TEXT = "镜头1：近景\n台词：一\n\n镜头2：远景\n台词：二"


class BatchShotImportTests(unittest.TestCase):
    def _project(self, directory):
        source = os.path.join(directory, "source.txt")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write("第01集\n正文一\n\n第02集\n正文二")
        return Project.create(directory, "demo", source)

    def _txt(self, directory, name, text=SHOT_TEXT, encoding="utf-8"):
        path = os.path.join(directory, name)
        with open(path, "w", encoding=encoding) as handle:
            handle.write(text)
        return path

    def test_numeric_names_map_to_project_episode_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(directory)
            imports = os.path.join(directory, "imports")
            os.makedirs(imports)
            one = self._txt(imports, "1.txt", encoding="gbk")
            two = self._txt(imports, "002.txt")
            invalid = self._txt(imports, "EP03.txt")

            analysis = BatchShotImporter().analyze(project, [one, two, invalid])
            self.assertEqual(analysis.items[0].target_episode, "01")
            self.assertEqual(analysis.items[1].target_episode, "02")
            self.assertEqual(analysis.items[0].shot_count, 2)
            self.assertEqual(analysis.items[2].status, "invalid")

    def test_duplicate_numeric_names_require_one_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(directory)
            first = os.path.join(directory, "a")
            second = os.path.join(directory, "b")
            os.makedirs(first)
            os.makedirs(second)
            one = self._txt(first, "1.txt")
            zero_one = self._txt(second, "01.txt")
            importer = BatchShotImporter()
            analysis = importer.analyze(project, [one, zero_one])
            self.assertTrue(all(item.status == "collision" for item in analysis.items))

            decisions = {item.item_id: "import" for item in analysis.items}
            with self.assertRaisesRegex(ValueError, "多个文件"):
                importer.apply(project, analysis, decisions)

    def test_apply_preserves_text_and_marks_only_visual_downstream_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(directory)
            project.set_artifact("01", "video", "completed", output_path="web_video/01")
            source = self._txt(directory, "1.txt")
            importer = BatchShotImporter()
            analysis = importer.analyze(project, [source])
            item = analysis.items[0]
            result = importer.apply(project, analysis, {item.item_id: "import"})
            self.assertTrue(result.success, result.error)
            with open(os.path.join(project.project_dir, "prompts", "01.txt"), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), SHOT_TEXT)
            reloaded = Project.load(project.project_dir)
            self.assertEqual(reloaded.manifest.get("01", "prompt").status, "completed")
            self.assertEqual(reloaded.manifest.get("01", "video").status, "stale")

    def test_apply_rolls_back_every_file_when_a_write_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(directory)
            imports = os.path.join(directory, "imports")
            os.makedirs(imports)
            one = self._txt(imports, "1.txt")
            two = self._txt(imports, "2.txt")
            prompts = os.path.join(project.project_dir, "prompts")
            os.makedirs(prompts, exist_ok=True)
            old = "镜头1：旧一\n\n镜头2：旧二"
            with open(os.path.join(prompts, "01.txt"), "w", encoding="utf-8") as handle:
                handle.write(old)

            importer = BatchShotImporter()
            analysis = importer.analyze(project, [one, two])
            decisions = {
                analysis.items[0].item_id: "replace",
                analysis.items[1].item_id: "import",
            }
            real_write = __import__(
                "core.batch_shot_import", fromlist=["_write_text_atomic"]
            )._write_text_atomic
            calls = 0

            def fail_second(path, content):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("synthetic failure")
                return real_write(path, content)

            with patch("core.batch_shot_import._write_text_atomic", side_effect=fail_second):
                result = importer.apply(project, analysis, decisions)
            self.assertFalse(result.success)
            with open(os.path.join(prompts, "01.txt"), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), old)
            self.assertFalse(os.path.exists(os.path.join(prompts, "02.txt")))


if __name__ == "__main__":
    unittest.main()
