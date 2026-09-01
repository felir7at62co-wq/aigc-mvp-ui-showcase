from agents.yunying_asset_generator import YunyingAssetGenerator


class FakeClient:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def generate_image(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return self.results.pop(0)

    def download(self, url, output_path):
        from PIL import Image
        Image.new("RGB", (8, 8), "blue").save(output_path, format="PNG")
        return output_path


def test_generator_saves_url_and_base64_results_as_png(tmp_path):
    from io import BytesIO
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
    client = FakeClient([{"bytes": buffer.getvalue()}, {"url": "https://cdn/b.png"}])
    generator = YunyingAssetGenerator(client)

    result = generator.process(
        descriptions=[
            {"name": "主角", "prompt": "中年女性，职业装"},
            {"name": "配角", "prompt": "年轻男性，休闲装"},
        ],
        output_dir=str(tmp_path),
        asset_type="character",
    )

    assert result == {"success": True, "generated": 2, "skipped": 0, "failed": 0, "errors": {}}
    assert (tmp_path / "主角.png").is_file()
    assert (tmp_path / "配角.png").is_file()
    assert all(call[1]["model"] == "gpt-image-2-official" for call in client.calls)
    assert all(call[1]["aspect_ratio"] == "1:1" for call in client.calls)
    assert "角色设定参考图" in client.calls[0][0]


def test_generator_skips_existing_and_reports_individual_failures(tmp_path):
    (tmp_path / "已有.png").write_bytes(b"existing")

    class FailingClient(FakeClient):
        def generate_image(self, prompt, **kwargs):
            raise RuntimeError("服务暂不可用")

    result = YunyingAssetGenerator(FailingClient([])).process(
        descriptions=[
            {"name": "已有", "prompt": "已有资产"},
            {"name": "失败", "prompt": "失败资产"},
        ],
        output_dir=str(tmp_path),
        asset_type="scene",
    )

    assert result["success"] is False
    assert result["skipped"] == 1
    assert result["failed"] == 1
    assert result["errors"] == {"失败": "服务暂不可用"}
