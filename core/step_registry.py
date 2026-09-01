"""Single source of truth for the current Web production workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class StepDefinition:
    id: str
    label: str
    page: str = ""
    dependencies: Tuple[str, ...] = ()
    output_dir: str = ""
    visible: bool = True


WEB_STEP_DEFINITIONS: Tuple[StepDefinition, ...] = (
    StepDefinition("import_script", "剧本导入与后台分集", dependencies=(), output_dir="episodes"),
    StepDefinition("prompt", "镜头脚本", dependencies=("import_script",), output_dir="prompts", visible=False),
    StepDefinition("asset", "资产生成", dependencies=("import_script",), output_dir="assets"),
    StepDefinition("shot_match", "镜头脚本与资产匹配", dependencies=("prompt", "asset"), output_dir="matches", visible=False),
    StepDefinition("video", "视频生成", dependencies=("shot_match",), output_dir="web_video"),
    StepDefinition("timeline", "视频轨道", dependencies=("video",), output_dir="timeline", visible=False),
    StepDefinition("preview", "视频预览", dependencies=("timeline",), output_dir="exports", visible=False),
    StepDefinition("export", "导出", dependencies=("timeline",), output_dir="exports", visible=False),
    StepDefinition("settings", "设置"),
)

STEP_DEFINITIONS = WEB_STEP_DEFINITIONS
STEP_BY_ID: Dict[str, StepDefinition] = {step.id: step for step in STEP_DEFINITIONS}
WEB_STEP_BY_ID = STEP_BY_ID
PRODUCTION_STEP_IDS: Tuple[str, ...] = tuple(
    step.id for step in STEP_DEFINITIONS if step.id != "settings"
)
WEB_PRODUCTION_STEP_IDS = PRODUCTION_STEP_IDS


def downstream_steps(
    step_id: str,
    definitions: Tuple[StepDefinition, ...] = STEP_DEFINITIONS,
) -> Tuple[str, ...]:
    """Return the selected step and all transitive dependants in registry order."""
    affected = {step_id}
    changed = True
    while changed:
        changed = False
        for step in definitions:
            if step.id not in affected and any(dep in affected for dep in step.dependencies):
                affected.add(step.id)
                changed = True
    return tuple(step.id for step in definitions if step.id in affected)
