from core.shot_match_manifest import build_match_manifest


def test_explicit_at_binding_uses_formal_asset_name():
    script = "镜头 1：\n出镜人物【婆婆@婆婆】\n核心场景：许家客厅"
    context = {
        "assets": {
            "character": [{"name": "婆婆", "episodes": ["01"]}],
            "scene": [{"name": "许家客厅", "episodes": ["01"]}],
            "prop": [],
        }
    }
    manifest = build_match_manifest(script, "01", context)
    item = manifest["shots"][0]["characters"][0]
    assert item["input"] == "婆婆@婆婆"
    assert item["name"] == "婆婆"
    assert item["matched"] is True
