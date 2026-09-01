"""每集 timeline.json 模型：原子读写、版本、校验、片段操作。"""
import json

from core.timeline import (
    Segment,
    TimelineManifest,
    Transition,
    build_initial_timeline,
    delete_segment,
    load_timeline,
    reorder_segments,
    restore_segment,
    save_timeline,
    set_transition,
    trim_segment,
    validate_timeline,
)


def _segment(
    seg_id="01-001",
    shot_id="shot-001",
    source_video="web_video/01/01-001.mp4",
    trim_in=0.0,
    trim_out=5.0,
    order=0,
    transition_to_next=None,
):
    return Segment(
        id=seg_id, shot_id=shot_id, source_video=source_video,
        prompt="镜头一", asset_ids=["character-main"], trim_in=trim_in,
        trim_out=trim_out, order=order,
        transition_to_next=transition_to_next or Transition(type="hard", duration=0.0),
    )


def test_build_initial_timeline_hard_cut_default():
    timeline = build_initial_timeline(
        episode_id="01", fps=30, width=1080, height=1920,
        videos=["web_video/01/01-001.mp4", "web_video/01/01-002.mp4"],
        durations=[5.0, 5.0],
    )
    assert timeline.version == 0          # 首次 save 后变为 1
    assert len(timeline.segments) == 2
    assert timeline.segments[0].order == 0
    assert timeline.segments[1].order == 1
    assert all(s.transition_to_next.type == "hard" for s in timeline.segments)
    assert timeline.segments[0].shot_id == "shot-001"
    assert timeline.segments[1].shot_id == "shot-002"
    assert timeline.segments[0].trim_out == 5.0  # 时长来自 durations


def test_validate_rejects_bad_trims():
    timeline = TimelineManifest(
        episode_id="01", segments=[
            _segment(trim_in=5.0, trim_out=5.0),   # 零时长
            _segment(seg_id="01-002", shot_id="shot-002",
                     source_video="x.mp4", trim_in=3.0, trim_out=2.0, order=1),  # 反向
        ],
    )
    errors = validate_timeline(timeline)
    assert any("01-001" in e and "时长" in e for e in errors)
    assert any("01-002" in e and "时长" in e for e in errors)


def test_validate_rejects_oversized_transition():
    timeline = TimelineManifest(
        episode_id="01", segments=[
            _segment(seg_id="01-001", trim_in=0.0, trim_out=2.0, order=0),
            _segment(seg_id="01-002", shot_id="shot-002", source_video="x.mp4",
                     trim_in=0.0, trim_out=2.0, order=1,
                     transition_to_next=Transition(type="crossfade", duration=3.0)),
        ],
    )
    errors = validate_timeline(timeline)
    assert any("转场" in e for e in errors)


def test_save_load_roundtrip_and_version_bump(tmp_path):
    timeline = build_initial_timeline("01", 30, 1080, 1920, ["a.mp4"], durations=[5.0])
    path = save_timeline(str(tmp_path), "01", timeline)   # 首次保存 -> version 1
    assert path.name == "01.json"
    loaded = load_timeline(str(tmp_path), "01")
    assert loaded == timeline
    assert loaded.version == 1
    loaded.segments[0].trim_out = 4.0
    save_timeline(str(tmp_path), "01", loaded)            # 第二次保存 -> version 2
    reloaded = load_timeline(str(tmp_path), "01")
    assert reloaded.version == 2
    assert reloaded.segments[0].trim_out == 4.0


def test_reorder_and_soft_delete_restore():
    timeline = build_initial_timeline("01", 30, 1080, 1920, ["a.mp4", "b.mp4"], durations=[5.0, 5.0])
    reorder_segments(timeline, ["01-002", "01-001"])
    assert [s.id for s in timeline.segments] == ["01-002", "01-001"]
    assert [s.order for s in timeline.segments] == [0, 1]
    delete_segment(timeline, "01-002")
    assert timeline.segments[0].deleted is True
    restore_segment(timeline, "01-002")
    assert timeline.segments[0].deleted is False


def test_set_transition_updates():
    timeline = build_initial_timeline("01", 30, 1080, 1920, ["a.mp4", "b.mp4"], durations=[5.0, 5.0])
    set_transition(timeline, "01-001", "crossfade", 0.35)
    assert timeline.segments[0].transition_to_next == Transition("crossfade", 0.35)
    assert validate_timeline(timeline) == []
