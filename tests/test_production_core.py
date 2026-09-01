import hashlib
import os
import tempfile
import unittest

from core.creative import AssetRecord, CreativeStore, ProjectBible, ShotRecord
from core.manifest import ArtifactRecord, ProjectManifest
from core.project import Project
from core.step_runner import StepRunner
from core.step_registry import downstream_steps


class ProductionCoreTests(unittest.TestCase):
    def _project(self, directory):
        source = os.path.join(directory, "source.txt")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write("第1集\n正文")
        return Project.create(directory, "demo", source)

    def test_downstream_registry_and_stale_propagation(self):
        self.assertEqual(
            downstream_steps("prompt"),
            ("prompt", "shot_match", "video", "timeline", "preview", "export"),
        )
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(directory)
            project.set_artifact("01", "prompt", "completed", input_hash="old")
            project.set_artifact("01", "video", "completed", input_hash="prompt")
            changed = project.mark_stale("01", "prompt")
            self.assertEqual(changed, ["prompt", "video"])
            reloaded = Project.load(project.project_dir)
            self.assertEqual(reloaded.manifest.get("01", "prompt").status, "stale")
            self.assertEqual(reloaded.manifest.get("01", "video").status, "stale")

    def test_screenplay_change_stales_visual_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(directory)
            project.sync_episode_hashes({"01": "first"})
            project.set_artifact("01", "asset", "completed", input_hash="source")
            project.set_artifact("01", "prompt", "completed", input_hash="source")
            project.sync_episode_hashes({"01": "changed"})
            self.assertEqual(project.manifest.get("01", "asset").status, "stale")
            self.assertEqual(project.manifest.get("01", "prompt").status, "stale")

    def test_manifest_is_atomic_and_recovers_from_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = ProjectManifest(directory)
            manifest.set("01", "script", ArtifactRecord(status="completed", input_hash="abc"))
            manifest.save()
            self.assertFalse(any(name.endswith(".tmp") for name in os.listdir(directory)))
            with open(manifest.path, "w", encoding="utf-8") as handle:
                handle.write("{")
            recovered = ProjectManifest(directory)
            self.assertEqual(recovered.data["episodes"], {})

    def test_step_runner_uses_exact_episode_whitelist_and_records_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(directory)
            visited = []

            def operation(_project, episode_id, _options, _cancelled):
                visited.append(episode_id)
                if episode_id == "03":
                    return {"success": False, "error": "synthetic"}
                return {"success": True, "status": "review", "output_path": f"{episode_id}.dat"}

            summary = StepRunner("video", operation).run(project, ["01", "03", "01"])
            self.assertEqual(visited, ["01", "03"])
            self.assertFalse(summary.success)
            self.assertEqual(summary.completed, 1)
            self.assertEqual(summary.failed, 1)
            self.assertEqual(project.manifest.get("03", "video").status, "failed")

    def test_creative_bible_and_confirmed_asset_versioning(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CreativeStore(directory)
            store.save_bible(ProjectBible(characters="林夏", pronunciations={"林夏": "lin xia"}))
            self.assertEqual(CreativeStore(directory).bible().characters, "林夏")
            store.put_asset(AssetRecord("char-linxia", "character", status="completed"))
            with self.assertRaisesRegex(ValueError, "更高版本"):
                store.put_asset(AssetRecord("char-linxia", "character", status="completed"))
            store.put_asset(AssetRecord("char-linxia", "character", version=2, status="review"))

    def test_shot_quality_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            warnings = CreativeStore(directory).put_shot(
                ShotRecord("01-001", "01", 20, scene="")
            )
            self.assertTrue(any("15" in warning for warning in warnings))
            self.assertTrue(any("场景" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
