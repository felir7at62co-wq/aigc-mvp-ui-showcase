"""资产 API（复用 core.asset_catalog）与镜头 API。"""
import io
import os
from types import SimpleNamespace

from PIL import Image


def _create(client, make_script, tmp_path, monkeypatch):
    monkeypatch.setattr("web_api.projects.PROJECTS_ROOT", str(tmp_path))
    script = make_script(1)
    with open(script, "rb") as handle:
        client.post("/api/projects", data={"name": "P", "script": (handle, "s.txt")},
                    content_type="multipart/form-data")


def test_asset_crud(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    response = client.post("/api/projects/P/assets", json={
        "category": "character", "name": "主角", "aliases": "阿主",
        "prompt": "一位穿白色风衣的年轻主角，电影感灯光。",
    })
    assert response.status_code == 201
    record = response.get_json()["asset"]
    assert record["name"] == "主角"
    # 重复创建同名应 400
    response = client.post("/api/projects/P/assets", json={
        "category": "character", "name": "主角",
        "prompt": "一位穿白色风衣的年轻主角，电影感灯光。",
    })
    assert response.status_code == 400
    response = client.post("/api/projects/P/assets/character/主角", json={
        "name": "主角",
        "aliases": "阿主", "prompt": "一位穿白色风衣的年轻主角，雨夜街景，电影感灯光。",
    })
    assert response.status_code == 200
    assert "雨夜" in response.get_json()["asset"]["prompt"]
    assert client.delete("/api/projects/P/assets/character/主角").status_code == 200


def test_asset_list_merges_prompt_records_and_image_only_assets(
    client, make_script, tmp_path, monkeypatch
):
    _create(client, make_script, tmp_path, monkeypatch)
    assets_dir = tmp_path / "P" / "assets"
    assets_dir.mkdir(exist_ok=True)
    (assets_dir / "character_prompts.txt").write_text(
        "主角|阿主|01,02|一位穿白色风衣的年轻主角，电影感灯光。\n",
        encoding="utf-8",
    )
    image_dir = assets_dir / "character"
    image_dir.mkdir(exist_ok=True)
    Image.new("RGB", (8, 8), "red").save(image_dir / "图片角色.png")

    response = client.get("/api/projects/P/assets")

    assert response.status_code == 200
    characters = response.get_json()["assets"]["character"]
    by_name = {item["name"]: item for item in characters}
    assert by_name["主角"]["aliases"] == ["阿主"]
    assert by_name["主角"]["episodes"] == ["01", "02"]
    assert by_name["图片角色"]["image_path"] == "assets/character/图片角色.png"
    assert by_name["图片角色"]["prompt"] == ""


def test_asset_image_upload_validates_and_installs_png(
    client, make_script, tmp_path, monkeypatch
):
    _create(client, make_script, tmp_path, monkeypatch)
    buffer = io.BytesIO()
    Image.new("RGB", (12, 10), "blue").save(buffer, format="JPEG")
    buffer.seek(0)

    response = client.post(
        "/api/projects/P/assets/character/主角/image",
        data={"file": (buffer, "portrait.jpg")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["image_path"] == "assets/character/主角.png"
    assert (tmp_path / "P" / "assets" / "character" / "主角.png").is_file()


def test_asset_image_upload_rejects_non_image(
    client, make_script, tmp_path, monkeypatch
):
    _create(client, make_script, tmp_path, monkeypatch)
    response = client.post(
        "/api/projects/P/assets/character/主角/image",
        data={"file": (io.BytesIO(b"not an image"), "bad.txt")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_asset_operation_filters_selected_category_and_names(
    client, make_script, tmp_path, monkeypatch
):
    _create(client, make_script, tmp_path, monkeypatch)
    from core.project import Project
    from web_api.operations import op_asset

    captured = []

    class FakeGenerator:
        def __init__(self, **_kwargs):
            pass

        def process(self, *, descriptions, asset_type, **_kwargs):
            captured.append((asset_type, [item["name"] for item in descriptions]))
            return {"success": True, "generated": len(descriptions)}

    monkeypatch.setattr("agents.yunying_asset_generator.YunyingAssetGenerator", FakeGenerator)
    monkeypatch.setattr("core.yunying_media_client.YunyingMediaClient", lambda **_kwargs: object())
    monkeypatch.setattr(
        "core.asset_context.load_or_build_asset_context",
        lambda _path: {"assets": {
            "character": [
                {"name": "主角", "prompt": "主角提示词"},
                {"name": "配角", "prompt": "配角提示词"},
            ],
            "scene": [{"name": "老街", "prompt": "老街提示词"}],
            "prop": [],
        }},
    )
    monkeypatch.setattr(
        "web_api.operations._config",
        lambda: SimpleNamespace(
            media=SimpleNamespace(
                api_key="x", base_url="http://example", timeout=1,
                poll_interval=0, request_timeout=1,
                video_model="seedance-2-0-official",
                image_model="gpt-image-2-official",
            ),
        ),
    )
    project = Project.load(str(tmp_path / "P"))

    result = op_asset(
        project,
        "01",
        {"category": "character", "asset_names": ["主角"]},
        lambda: False,
    )

    assert result["success"] is True
    assert captured == [("character", ["主角"])]

    captured.clear()
    result = op_asset(project, "01", {}, lambda: False)
    assert result["success"] is True
    assert captured == [
        ("character", ["主角", "配角"]),
        ("scene", ["老街"]),
    ]


def test_shot_script_and_match(client, make_script, tmp_path, monkeypatch):
    _create(client, make_script, tmp_path, monkeypatch)
    prompts = os.path.join(str(tmp_path), "P", "prompts")
    os.makedirs(prompts, exist_ok=True)
    with open(os.path.join(prompts, "01.txt"), "w", encoding="utf-8") as handle:
        handle.write("镜头 1：主角登场\n出镜人物【主角】\n核心场景：办公室\n")
    response = client.get("/api/projects/P/shots/01")
    assert response.status_code == 200
    assert "镜头 1" in response.get_json()["script"]
    assert response.get_json()["match"] is None  # 尚无匹配清单
    # 生成匹配清单后再查
    from core.asset_context import load_or_build_asset_context
    from core.shot_match_manifest import build_match_manifest, save_match_manifest
    with open(os.path.join(prompts, "01.txt"), "r", encoding="utf-8") as handle:
        script = handle.read()
    context = load_or_build_asset_context(str(tmp_path / "P"))
    save_match_manifest(str(tmp_path / "P"), "01",
                        build_match_manifest(script, "01", context))
    payload = client.get("/api/projects/P/shots/01").get_json()
    assert payload["match"]["episode"] == "01"
