"""Generate reusable character, scene, and prop assets with GPT Image 2."""

from __future__ import annotations

from io import BytesIO
import os
import tempfile
from typing import Any, Iterable, Mapping

from PIL import Image


class YunyingAssetGenerator:
    CATEGORY_PREFIXES = {
        "character": "角色设定参考图，完整人物，全身与关键细节清晰，纯净背景，保持身份与服装一致。",
        "scene": "场景设定参考图，空间结构明确，光线与材质细节清晰，无文字水印。",
        "prop": "道具设定参考图，主体完整，形状材质清晰，纯净背景，无文字水印。",
    }

    def __init__(self, client, image_model: str = "gpt-image-2-official") -> None:
        self.client = client
        self.image_model = image_model

    def process(
        self,
        *,
        descriptions: Iterable[Mapping[str, Any]],
        output_dir: str,
        asset_type: str,
        **_: Any,
    ) -> dict[str, Any]:
        os.makedirs(output_dir, exist_ok=True)
        result: dict[str, Any] = {
            "success": True, "generated": 0, "skipped": 0,
            "failed": 0, "errors": {},
        }
        prefix = self.CATEGORY_PREFIXES.get(asset_type, "资产设定参考图，主体完整清晰，无文字水印。")
        for record in descriptions:
            name = os.path.basename(str(record.get("name", "")).strip())
            prompt = str(record.get("prompt") or record.get("desc") or "").strip()
            if not name or not prompt:
                continue
            output_path = os.path.join(output_dir, f"{name}.png")
            if os.path.isfile(output_path):
                result["skipped"] += 1
                continue
            try:
                generated = self.client.generate_image(
                    f"{prefix}\n{prompt}",
                    model=self.image_model,
                    aspect_ratio="1:1",
                    resolution="2k",
                    quality="high",
                )
                self._save_result_as_png(generated, output_path)
                result["generated"] += 1
            except Exception as exc:
                result["success"] = False
                result["failed"] += 1
                result["errors"][name] = str(exc)
        return result

    def _save_result_as_png(self, generated: Mapping[str, Any], output_path: str) -> None:
        directory = os.path.dirname(output_path)
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=directory, suffix=".image") as handle:
            temporary_source = handle.name
            if isinstance(generated.get("bytes"), bytes):
                handle.write(generated["bytes"])
        try:
            if generated.get("url"):
                self.client.download(str(generated["url"]), temporary_source)
            with Image.open(temporary_source) as image:
                converted = image.convert("RGBA" if image.mode in {"RGBA", "LA"} else "RGB")
                with tempfile.NamedTemporaryFile("wb", delete=False, dir=directory, suffix=".png") as target:
                    temporary_png = target.name
                converted.save(temporary_png, format="PNG")
            os.replace(temporary_png, output_path)
        finally:
            try:
                os.remove(temporary_source)
            except OSError:
                pass
