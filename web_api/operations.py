"""步骤操作注册表：StepRunner 契约 (project, episode_id, options, cancelled) -> dict。"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict

from core.config import load_config
from core.llm_client import get_shared_llm_client
from core.paths import get_config_path, get_prompts_dir
from core.project import Project
from core.script_source import ProjectScriptSource

Operation = Callable[..., Dict[str, Any]]


def _config():
    return load_config(get_config_path())


def _llm():
    config = _config()
    return get_shared_llm_client(
        api_key=config.llm.api_key,
        base_url=config.llm.base_url,
        model=config.llm.model,
        max_tokens=config.llm.max_tokens,
        temperature=config.llm.temperature,
    )


def op_prompt(project: Project, episode_id: str, options: Dict[str, Any], cancelled) -> Dict[str, Any]:
    """提示词提取：LLM 生成镜头脚本 prompts/{ep}.txt。"""
    from agents.prompt_generator import PromptBuilder, PromptGenerator
    source = ProjectScriptSource(project.project_dir)
    source.ensure()
    prompts_dir = project.get_step_dir("prompt")
    config = _config()
    generator = PromptGenerator(
        _llm(),
        PromptBuilder.from_file(os.path.join(get_prompts_dir(), "default_shot_prompt.txt")),
        context_window=config.llm.context_window,
    )
    result = generator.process(
        episodes_dir=source.visual_episodes_dir(),
        output_dir=prompts_dir,
        skip_existing=True,
        selected_episodes=[episode_id],
    )
    if not result.get("success"):
        return {"success": False, "error": result.get("error", "镜头脚本生成失败")}
    path = os.path.join("prompts", f"{int(episode_id):02d}.txt")
    return {"success": True, "status": "completed", "output_path": path,
            "metadata": {"generated": result.get("generated", 0)}}


def op_shot_match(project: Project, episode_id: str, options: Dict[str, Any], cancelled) -> Dict[str, Any]:
    """镜头脚本与资产匹配：matches/{ep}.json。"""
    from core.asset_context import load_or_build_asset_context
    from core.shot_match_manifest import build_match_manifest, save_match_manifest
    prompts_dir = project.get_step_dir("prompt")
    script_path = os.path.join(prompts_dir, f"{int(episode_id):02d}.txt")
    if not os.path.isfile(script_path):
        return {"success": False, "error": f"缺少镜头脚本: {script_path}"}
    with open(script_path, "r", encoding="utf-8") as handle:
        shot_script = handle.read()
    context = load_or_build_asset_context(project.project_dir)
    manifest = build_match_manifest(shot_script, episode_id, context)
    path = save_match_manifest(project.project_dir, episode_id, manifest)
    relative = os.path.relpath(path, project.project_dir).replace("\\", "/")
    return {"success": True, "status": "completed", "output_path": relative,
            "metadata": {"shots": len(manifest.get("shots", []))}}


def op_asset(project: Project, episode_id: str, options: Dict[str, Any], cancelled) -> Dict[str, Any]:
    """资产生成：使用 GPT Image 2 为缺失资产生成 PNG。"""
    from agents.yunying_asset_generator import YunyingAssetGenerator
    from core.asset_context import load_or_build_asset_context
    from core.yunying_media_client import YunyingMediaClient
    config = _config()
    context = load_or_build_asset_context(project.project_dir)
    assets = context.get("assets", {})
    client = YunyingMediaClient(
        api_key=config.media.api_key,
        base_url=config.media.base_url,
        video_model=config.media.video_model,
        image_model=config.media.image_model,
        timeout=config.media.timeout,
        poll_interval=config.media.poll_interval,
        request_timeout=config.media.request_timeout,
    )
    generator = YunyingAssetGenerator(client=client, image_model=config.media.image_model)
    requested_category = str(options.get("category") or "").strip()
    if requested_category and requested_category not in {"character", "scene", "prop"}:
        return {"success": False, "error": f"不支持的资产类别: {requested_category}"}
    requested_names = {
        str(value).strip()
        for value in (options.get("asset_names") or [])
        if str(value).strip()
    }
    generated = 0
    for asset_type in ("character", "scene", "prop"):
        if requested_category and asset_type != requested_category:
            continue
        records = assets.get(asset_type, []) or []
        missing = [
            {"name": item.get("name", ""), "prompt": item.get("prompt", item.get("desc", ""))}
            for item in records
            if item.get("name")
            and (not requested_names or item.get("name") in requested_names)
            and not os.path.isfile(
                os.path.join(project.project_dir, "assets", asset_type, f"{item['name']}.png"))
        ]
        if not missing:
            continue
        result = generator.process(
            descriptions=missing,
            output_dir=os.path.join(project.project_dir, "assets", asset_type),
            asset_type=asset_type,
        )
        generated += int(result.get("generated", 0))
        if not result.get("success"):
            return {"success": False, "error": result.get("error", "资产生成失败")}
    return {"success": True, "status": "completed", "output_path": "assets",
            "metadata": {"generated": generated}}


def op_video(project: Project, episode_id: str, options: Dict[str, Any], cancelled) -> Dict[str, Any]:
    """Generate 15-second reference-video batches, then split them per shot."""
    from core.ffmpeg_runner import FFmpegRunner
    from core.project_settings import load_project_settings
    from core.shot_match_manifest import load_match_manifest
    from core.video_batches import build_batch_prompt, group_shots, parse_shot_blocks
    from core.yunying_media_client import YunyingMediaClient

    config = _config()
    manifest = load_match_manifest(project.project_dir, episode_id)
    if manifest is None:
        return {"success": False, "error": f"缺少镜头匹配清单: matches/{int(episode_id):02d}.json"}
    script_path = os.path.join(project.get_step_dir("prompt"), f"{int(episode_id):02d}.txt")
    if not os.path.isfile(script_path):
        return {"success": False, "error": f"缺少镜头脚本: prompts/{int(episode_id):02d}.txt"}
    with open(script_path, "r", encoding="utf-8") as handle:
        shot_blocks = parse_shot_blocks(handle.read())
    if not shot_blocks:
        return {"success": False, "error": "镜头脚本中没有可识别的镜头"}

    requested = {int(value) for value in (options.get("shots") or [])} or None
    if requested is not None:
        shot_blocks = [shot for shot in shot_blocks if shot.number in requested]
    settings = load_project_settings(project.project_dir)
    output_dir = project.get_episode_dir("web_video", int(episode_id))
    batch_dir = os.path.join(output_dir, ".batches")
    os.makedirs(batch_dir, exist_ok=True)
    client = YunyingMediaClient(
        api_key=config.media.api_key,
        base_url=config.media.base_url,
        video_model=config.media.video_model,
        image_model=config.media.image_model,
        timeout=config.media.timeout,
        poll_interval=config.media.poll_interval,
        request_timeout=config.media.request_timeout,
    )
    runner = FFmpegRunner(config.ffmpeg_path)
    manifest_by_number = {
        int(shot.get("shot", 0)): shot for shot in manifest.get("shots", [])
        if int(shot.get("shot", 0)) > 0
    }
    upload_cache: dict[str, str] = {}
    generated = 0
    completed_batches = 0
    for batch_index, batch in enumerate(group_shots(shot_blocks), start=1):
        if _is_cancelled(cancelled):
            return {"success": False, "status": "cancelled"}
        output_paths = [os.path.join(output_dir, f"{shot.number:03d}.mp4") for shot in batch]
        if requested is None and all(os.path.isfile(path) for path in output_paths):
            generated += len(batch)
            continue
        reference_paths = _batch_reference_paths(
            project.project_dir,
            [manifest_by_number.get(shot.number, {}) for shot in batch],
        )
        if not reference_paths:
            numbers = "、".join(f"{shot.number:03d}" for shot in batch)
            return {"success": False, "error": f"镜头 {numbers} 缺少可用的资产参考图"}
        try:
            image_urls = []
            for path in reference_paths:
                if path not in upload_cache:
                    upload_cache[path] = client.upload_file(path)
                image_urls.append(upload_cache[path])
            batch_path = os.path.join(batch_dir, f"batch-{batch_index:03d}.mp4")
            client.generate_video_and_wait(
                prompt=build_batch_prompt(batch, settings["prompt_prefix"]),
                images=image_urls,
                output_path=batch_path,
                duration=15,
                resolution=settings["resolution"],
                aspect_ratio=settings["aspect_ratio"],
                mode="reference",
                model=settings["video_model"],
                cancel_event=cancelled if hasattr(cancelled, "is_set") else None,
            )
            runner.split_segments(
                batch_path,
                [(f"{shot.number:03d}.mp4", shot.duration) for shot in batch],
                output_dir,
            )
        except Exception as exc:
            numbers = "、".join(f"{shot.number:03d}" for shot in batch)
            return {"success": False, "error": f"镜头批次 {numbers} 生成失败: {exc}"}
        generated += len(batch)
        completed_batches += 1
    relative = os.path.relpath(output_dir, project.project_dir).replace("\\", "/")
    return {"success": True, "status": "completed", "output_path": relative,
            "metadata": {"generated": generated, "batches": completed_batches}}


def _is_cancelled(cancelled) -> bool:
    if hasattr(cancelled, "is_set"):
        return bool(cancelled.is_set())
    return bool(cancelled()) if callable(cancelled) else False


def _batch_reference_paths(project_dir: str, shots: list[Dict[str, Any]]) -> list[str]:
    candidates: list[tuple[str, str]] = []
    for shot in shots:
        for character in shot.get("characters", []) or []:
            if character.get("name"):
                candidates.append(("character", str(character["name"])))
        scene = shot.get("scene", {}) or {}
        if scene.get("name"):
            candidates.append(("scene", str(scene["name"])))
        for prop in shot.get("props", []) or []:
            if prop.get("name"):
                candidates.append(("prop", str(prop["name"])))
    paths: list[str] = []
    seen: set[str] = set()
    for category, name in candidates:
        for extension in (".png", ".jpg", ".jpeg", ".webp"):
            path = os.path.join(project_dir, "assets", category, f"{name}{extension}")
            if os.path.isfile(path):
                absolute = os.path.abspath(path)
                if absolute not in seen:
                    seen.add(absolute)
                    paths.append(absolute)
                break
    # Seedance 2.0 reference mode accepts at most nine images per task.
    return paths[:9]


OPERATIONS: Dict[str, Operation] = {
    "prompt": op_prompt,
    "asset": op_asset,
    "shot_match": op_shot_match,
    "video": op_video,
}


def op_preview(project: Project, episode_id: str, options: Dict[str, Any], cancelled) -> Dict[str, Any]:
    """成片预览渲染：timeline -> exports/{ep}_preview.mp4。"""
    from core.timeline_render import render_preview_with_manifest
    result = render_preview_with_manifest(project.project_dir, episode_id)
    if not result["success"]:
        return {"success": False, "error": result["error"]}
    relative = os.path.relpath(result["preview_path"], project.project_dir).replace("\\", "/")
    return {"success": True, "status": "completed", "output_path": relative,
            "metadata": {"duration": round(result["duration"], 3)}}


def op_export(project: Project, episode_id: str, options: Dict[str, Any], cancelled) -> Dict[str, Any]:
    """双交付导出：timeline -> 剪映工程。"""
    from core.export_jianying import export_jianying
    result = export_jianying(
        project.project_dir,
        episode_id,
        drafts_dir=options.get("drafts_dir") or _config().draft_output_dir,
        prefix=options.get("prefix", ""),
    )
    if not result["success"]:
        return {"success": False, "error": result["error"]}
    return {"success": True, "status": "completed", "output_path": result["draft_path"],
            "metadata": {"draft_name": result["draft_name"]}}


OPERATIONS["preview"] = op_preview
OPERATIONS["export"] = op_export
