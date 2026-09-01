from core.asset_context import build_asset_context
from core.shot_match_manifest import (
    build_match_manifest,
    manifest_names,
    prune_orphan_match_manifests,
    save_match_manifest,
)


def test_legacy_scene_scope_is_inferred_from_episode_text(tmp_path):
    (tmp_path / "episodes").mkdir()
    (tmp_path / "assets").mkdir()
    (tmp_path / "episodes" / "01.txt").write_text("他们来到宴会厅。", encoding="utf-8")
    (tmp_path / "episodes" / "02.txt").write_text("回到家中。", encoding="utf-8")
    (tmp_path / "assets" / "scene_prompts.txt").write_text(
        "宴会厅|宴会||宴会厅写实场景\n", encoding="utf-8"
    )
    context = build_asset_context(str(tmp_path))
    assert context["assets"]["scene"][0]["episodes"] == ["01"]


def test_manifest_resolves_aliases_and_keeps_unmatched_scene_text_only():
    context = {
        "assets": {
            "character": [{
                "name": "公公", "aliases": ["老爷子"],
                "strong_aliases": ["老爷子"], "episodes": ["02"],
            }],
            "scene": [{
                "name": "宴会厅", "aliases": ["宴会"],
                "strong_aliases": ["宴会"], "episodes": ["02"],
            }],
            "prop": [],
        }
    }
    script = (
        "镜头1：\n出镜人物【老爷子】\n核心场景：宴会\n"
        "镜头2：\n出镜人物【公公】\n核心场景：三甲医院\n"
    )
    manifest = build_match_manifest(script, "02", context)
    assert manifest["shots"][0]["characters"][0]["name"] == "公公"
    assert manifest["shots"][0]["scene"]["name"] == "宴会厅"
    assert manifest["shots"][1]["scene"]["matched"] is False
    assert manifest_names(manifest)[1] == {"宴会厅"}


def test_manifest_prefers_episode_scoped_character_variant_over_base_name():
    context = {
        "assets": {
            "character": [
                {"name": "江蓁", "aliases": [], "strong_aliases": [], "episodes": ["13", "14"]},
                {
                    "name": "江蓁寿宴服装",
                    "aliases": ["江蓁"],
                    "strong_aliases": ["江蓁"],
                    "episodes": ["13"],
                },
            ],
            "scene": [],
            "prop": [],
        }
    }
    script = "镜头1：\n出镜人物【江蓁】\n核心场景：中餐厅豪华包厢\n"

    episode_13 = build_match_manifest(script, "13", context)
    episode_14 = build_match_manifest(script, "14", context)

    assert episode_13["shots"][0]["characters"][0]["name"] == "江蓁寿宴服装"
    assert episode_14["shots"][0]["characters"][0]["name"] == "江蓁"


def test_prune_orphan_match_manifests_deletes_matches_without_prompt(tmp_path):
    (tmp_path / "prompts").mkdir()
    save_match_manifest(str(tmp_path), "01", {"episode": "01", "shots": []})
    save_match_manifest(str(tmp_path), "02", {"episode": "02", "shots": []})
    (tmp_path / "prompts" / "01.txt").write_text("镜头1：\n", encoding="utf-8")

    removed = prune_orphan_match_manifests(str(tmp_path))

    assert removed == 1
    assert (tmp_path / "matches" / "01.json").is_file()
    assert not (tmp_path / "matches" / "02.json").exists()
