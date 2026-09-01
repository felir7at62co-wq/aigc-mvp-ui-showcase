"""Render a timeline manifest into a preview video."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from core.ffmpeg_runner import FFmpegError, FFmpegRunner
from core.timeline import Segment, TimelineManifest, load_timeline


@dataclass
class RenderResult:
    success: bool
    preview_path: str = ""
    duration: float = 0.0
    error: str = ""


def render_preview(
    project_dir: str,
    episode_id: str,
    output_name: Optional[str] = None,
) -> RenderResult:
    runner = FFmpegRunner()
    timeline = load_timeline(project_dir, episode_id)
    if timeline is None:
        return RenderResult(success=False, error=f"Timeline not found: {episode_id}")
    work_dir = ""
    temp_path = ""
    try:
        segments = _active_segments(timeline)
        if not segments:
            return RenderResult(success=False, error="Timeline has no active segments")
        work_dir = _work_dir(project_dir)
        trimmed = [
            _trim_clip(runner, project_dir, segment, work_dir)
            for segment in segments
        ]
        preview_path = _preview_path(project_dir, episode_id, output_name)
        os.makedirs(os.path.dirname(preview_path), exist_ok=True)
        temp_path = preview_path + ".rendering.mp4"
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if _has_transitions(segments):
            _render_with_transitions(runner, trimmed, temp_path, segments, timeline)
        else:
            _concat_hard_cuts(runner, trimmed, temp_path)
        probe = runner.probe(temp_path)
        duration = probe["duration"] if probe else 0.0
        os.replace(temp_path, preview_path)
        _cleanup(trimmed)
        return RenderResult(success=True, preview_path=preview_path, duration=duration)
    except FFmpegError as exc:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        if work_dir:
            _cleanup_work(work_dir)
        return RenderResult(success=False, error=str(exc))


def _active_segments(timeline: TimelineManifest) -> List[Segment]:
    segments = [segment for segment in timeline.segments if not segment.deleted]
    segments.sort(key=lambda segment: segment.order)
    return segments


def _trim_clip(
    runner: FFmpegRunner,
    project_dir: str,
    segment: Segment,
    work_dir: str,
) -> str:
    source = os.path.join(project_dir, segment.source_video.replace("/", os.sep))
    if not os.path.isfile(source):
        raise FFmpegError(f"Source video not found: {segment.source_video}")
    output = os.path.join(work_dir, f"{segment.id}.mp4")
    duration = segment.duration
    if duration <= 0:
        raise FFmpegError(f"{segment.id}: segment duration must be positive")
    runner.run([
        "-ss", f"{segment.trim_in:.3f}",
        "-i", source,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-an",
        "-y", output,
    ])
    return output


def _has_transitions(segments: List[Segment]) -> bool:
    return any(
        segment.transition_to_next.type != "hard"
        for segment in segments[:-1]
    )


def _concat_hard_cuts(
    runner: FFmpegRunner,
    trimmed: List[str],
    preview_path: str,
) -> None:
    if len(trimmed) == 1:
        runner.run(["-i", trimmed[0], "-c", "copy", "-y", preview_path])
        return
    list_file = os.path.join(os.path.dirname(preview_path), "concat.txt")
    with open(list_file, "w", encoding="utf-8") as handle:
        for path in trimmed:
            escaped = path.replace("'", "'\\''")
            handle.write(f"file '{escaped}'\n")
    runner.run([
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        "-y", preview_path,
    ])
    try:
        os.remove(list_file)
    except OSError:
        pass


def _work_dir(project_dir: str) -> str:
    directory = os.path.join(project_dir, "exports", "tmp")
    os.makedirs(directory, exist_ok=True)
    return directory


def _preview_path(
    project_dir: str,
    episode_id: str,
    output_name: Optional[str],
) -> str:
    exports = os.path.join(project_dir, "exports")
    os.makedirs(exports, exist_ok=True)
    filename = output_name or f"{int(episode_id):02d}_preview.mp4"
    return os.path.join(exports, filename)


def _cleanup(trimmed: List[str]) -> None:
    for path in trimmed:
        try:
            os.remove(path)
        except OSError:
            pass


def _cleanup_work(work_dir: str) -> None:
    try:
        for name in os.listdir(work_dir):
            os.remove(os.path.join(work_dir, name))
    except OSError:
        pass


def _render_with_transitions(
    runner: FFmpegRunner,
    trimmed: List[str],
    preview_path: str,
    segments: List[Segment],
    timeline: TimelineManifest,
) -> None:
    """Apply fade filters, concatenate hard-cut groups, then chain xfade."""
    fades = [_fade_args(segment) for segment in segments]
    faded: List[str] = []
    for index, path in enumerate(trimmed):
        fade_out, fade_in = fades[index]
        if fade_out <= 0 and fade_in <= 0:
            faded.append(path)
            continue
        output = path.replace(".mp4", ".faded.mp4")
        filters = []
        if fade_in > 0:
            filters.append(f"fade=t=in:st=0:d={fade_in:.3f}")
        if fade_out > 0:
            filters.append(
                f"fade=t=out:st={_fade_out_start(segments[index], fade_out):.3f}:d={fade_out:.3f}"
            )
        runner.run([
            "-i", path,
            "-vf", ",".join(filters),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-an",
            "-y", output,
        ])
        faded.append(output)

    groups: List[List[int]] = []
    for index in range(len(faded)):
        if not groups or segments[groups[-1][-1]].transition_to_next.type == "crossfade":
            groups.append([index])
        else:
            groups[-1].append(index)

    group_clips: List[str] = []
    for group in groups:
        if len(group) == 1:
            group_clips.append(faded[group[0]])
            continue
        group_path = os.path.join(
            os.path.dirname(faded[group[0]]),
            f"group{len(group_clips)}.mp4",
        )
        _concat_hard_cuts(runner, [faded[index] for index in group], group_path)
        group_clips.append(group_path)

    if len(group_clips) == 1:
        runner.run(["-i", group_clips[0], "-c", "copy", "-y", preview_path])
        return

    durations = []
    for path in group_clips:
        probe = runner.probe(path)
        if not probe:
            raise FFmpegError(f"Unable to probe transition clip: {path}")
        durations.append(probe["duration"])
    xfades = [
        segments[groups[index][-1]].transition_to_next
        for index in range(len(groups) - 1)
    ]
    offsets: List[float] = []
    offset = 0.0
    for index, xfade in enumerate(xfades):
        offsets.append(max(0.0, offset + durations[index] - xfade.duration))
        offset = offsets[-1]

    filter_parts: List[str] = []
    previous = "0:v"
    for index in range(1, len(group_clips)):
        transition = xfades[index - 1]
        output_label = f"x{index}"
        filter_parts.append(
            f"[{previous}][{index}:v]xfade=transition=fade:"
            f"duration={transition.duration:.3f}:offset={offsets[index - 1]:.3f}[{output_label}]"
        )
        previous = output_label
    filter_parts.append(f"[{previous}]format=yuv420p[vout]")

    inputs: List[str] = []
    for path in group_clips:
        inputs.extend(["-i", path])
    runner.run([
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", "[vout]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-an",
        "-y", preview_path,
    ])


def _fade_args(segment: Segment) -> tuple[float, float]:
    transition = segment.transition_to_next
    if transition.type == "fade_black":
        return transition.duration, 0.0
    return 0.0, 0.0


def _fade_out_start(segment: Segment, duration: float) -> float:
    return max(0.0, segment.duration - duration)

def render_preview_with_manifest(project_dir: str, episode_id: str) -> dict:
    """Render preview and persist the outcome into the manifest's preview record.

    On failure the previous output_path is preserved so the frontend can still
    play the last good preview.
    """
    from core.manifest import ArtifactRecord, ProjectManifest

    manifest = ProjectManifest(project_dir)
    previous = manifest.get(episode_id, "preview")
    result = render_preview(project_dir, episode_id)
    episode = str(episode_id).zfill(2)
    if result.success:
        relative = os.path.relpath(result.preview_path, project_dir).replace("\\", "/")
        manifest.set(episode, "preview", ArtifactRecord(
            status="completed", output_path=relative,
            metadata={"duration": round(result.duration, 3)},
        ))
    else:
        manifest.set(episode, "preview", ArtifactRecord(
            status="failed",
            output_path=previous.output_path,
            error=result.error[:500],
        ))
    manifest.save()
    return {
        "success": result.success,
        "preview_path": result.preview_path,
        "duration": result.duration,
        "error": result.error,
    }
