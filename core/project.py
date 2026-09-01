"""
AIGC Pipeline — 项目目录管理 & 状态持久化

项目目录只创建当前 Web 工作台所需的剧本、资产、镜头脚本、视频与导出目录。
"""
import os
import json
import time
import logging
import tempfile
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

from core.manifest import ArtifactRecord, ProjectManifest

logger = logging.getLogger(__name__)


# 步骤定义
STEPS = ["script", "asset", "prompt", "web_video", "draft"]

WEB_STEPS = (
    "import_script", "prompt", "asset", "shot_match",
    "video", "timeline", "preview", "export",
)

_LEGACY_WEB_MAP = {
    "script": "import_script",
    "prompt": "prompt",
    "asset": "asset",
    "web_video": "video",
    "draft": "export",
}


def migrate_legacy_state(project_dir: str) -> Dict[str, Dict[str, Any]]:
    """Return a Web step status view without modifying the legacy state file."""
    view: Dict[str, Dict[str, Any]] = {
        step: {"status": "pending", "error": None, "output_count": 0}
        for step in WEB_STEPS
    }
    state_file = os.path.join(project_dir, "state.json")
    if not os.path.isfile(state_file):
        return view
    try:
        with open(state_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return view

    steps_data = data.get("steps", {})
    for legacy, web in _LEGACY_WEB_MAP.items():
        if web is None:
            continue
        record = steps_data.get(legacy)
        if not isinstance(record, dict):
            continue
        view[web] = {
            "status": record.get("status", "pending"),
            "error": record.get("error"),
            "output_count": record.get("output_count", 0),
            "legacy_step": legacy,
        }
    return view

# 每个步骤的输出目录
STEP_DIRS = {
    "script": "episodes",
    "prompt": "prompts",
    "asset": "assets",
    "web_video": "web_video",
    "draft": "draft",
}


@dataclass
class StepState:
    """单步骤的状态"""
    status: str = "pending"        # pending / running / completed / failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    output_count: int = 0          # 输出文件数
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectState:
    """项目状态"""
    name: str = ""
    script_path: str = ""
    script_mtime: float = 0.0  # 剧本文件最后修改时间
    created_at: str = ""
    updated_at: str = ""
    episode_count: int = 0
    steps: Dict[str, StepState] = field(default_factory=dict)

    def __post_init__(self):
        # 确保所有步骤都有状态
        for step in STEPS:
            if step not in self.steps:
                self.steps[step] = StepState()


class Project:
    """
    项目管理器

    负责:
      1. 创建/加载项目目录
      2. 管理步骤状态 (state.json)
      3. 提供各步骤的输入/输出路径
    """

    def __init__(self, project_dir: str):
        self.project_dir = os.path.abspath(project_dir)
        self.state_file = os.path.join(self.project_dir, "state.json")
        self.state = ProjectState()
        self.manifest = ProjectManifest(self.project_dir)

    @classmethod
    def create(
        cls,
        project_root: str,
        name: str,
        script_path: str,
    ) -> "Project":
        """
        创建新项目

        参数:
            project_root: 项目根目录 (如 ./projects)
            name: 项目名称 (用作目录名)
            script_path: 剧本文件路径
        """
        # 清理项目名（去除不安全字符）
        safe_name = "".join(
            c for c in name if c.isalnum() or c in ("-", "_", ".", " ", "（", "）")
        ).strip()
        if not safe_name:
            safe_name = f"project_{int(time.time())}"

        project_dir = os.path.join(project_root, safe_name)

        proj = cls(project_dir)
        proj.state.name = safe_name
        from core.script_source import ProjectScriptSource
        proj._ensure_dirs()
        proj.state.script_path = ProjectScriptSource(project_dir).initialize(script_path)
        if os.path.exists(proj.state.script_path):
            proj.state.script_mtime = os.path.getmtime(proj.state.script_path)
        proj.state.created_at = datetime.now().isoformat()
        proj.state.updated_at = proj.state.created_at

        # 创建目录结构
        proj._save_state()
        proj.manifest.data["project"] = {
            "name": safe_name,
            "script_path": proj.state.script_path,
            "source_sha256": ProjectScriptSource(project_dir).source_hash(),
            "created_at": proj.state.created_at,
        }
        proj.manifest.save()

        logger.info(f"项目已创建: {project_dir}")
        return proj

    @classmethod
    def load(cls, project_dir: str, script_path: Optional[str] = None) -> "Project":
        """加载已有项目"""
        proj = cls(project_dir)
        if os.path.exists(proj.state_file):
            proj._load_state()
            from core.script_source import ProjectScriptSource
            source = ProjectScriptSource(project_dir)
            source.ensure(proj.state.script_path or script_path or "")
            original_candidates = [
                os.path.join(source.source_dir, name)
                for name in os.listdir(source.source_dir)
                if name.startswith("original.")
            ]
            if original_candidates and proj.state.script_path != original_candidates[0]:
                proj.state.script_path = original_candidates[0]
                proj.state.script_mtime = os.path.getmtime(proj.state.script_path)
                proj._save_state()
            if script_path and os.path.isfile(script_path):
                from agents.script_processor import read_script
                import hashlib
                incoming_hash = hashlib.sha256(
                    read_script(script_path)["text"].encode("utf-8")
                ).hexdigest()
                if incoming_hash != source.source_hash():
                    logger.info("检测到新剧本，更新项目源并标记下游结果过期: %s", script_path)
                    proj.state.script_path = source.initialize(script_path)
                    proj.state.script_mtime = os.path.getmtime(proj.state.script_path)
                    for step_name, state in proj.state.steps.items():
                        if step_name != "project" and state.status == "completed":
                            state.status = "stale"
                            state.error = "项目原始剧本已更新"
                    for episode_data in proj.manifest.data.setdefault("episodes", {}).values():
                        for record in episode_data.values():
                            if isinstance(record, dict) and (
                                record.get("status") != "pending"
                                or record.get("input_hash")
                                or record.get("output_path")
                            ):
                                record["status"] = "stale"
                                record["error"] = "项目原始剧本已更新"
                    proj.manifest.data.setdefault("project", {})["script_path"] = proj.state.script_path
                    proj.manifest.data["project"]["source_sha256"] = source.source_hash()
                    proj.manifest.save()
                    proj._save_state()
            # 如果提供了新的剧本路径，检查并更新
            if script_path:
                new_script_path = os.path.abspath(script_path)
                if proj.state.script_path != new_script_path:
                    # 检查旧路径是否存在，不存在则更新为新路径
                    if not os.path.exists(proj.state.script_path) and os.path.exists(new_script_path):
                        logger.info(f"更新剧本路径: {proj.state.script_path} -> {new_script_path}")
                        proj.state.script_path = new_script_path
                        proj._save_state()
            # 检查剧本文件是否已更新
            if proj.is_script_updated():
                logger.warning("检测到剧本文件已更新")
                # 重置与剧本直接相关的步骤的状态
                for step in ["script", "prompt", "asset"]:
                    if proj.state.steps[step].status == "completed":
                        logger.info(f"重置步骤 '{step}' 的状态为待执行")
                        proj.state.steps[step].status = "pending"
                        proj.state.steps[step].completed_at = None
                        proj.state.steps[step].output_count = 0
                        proj.state.steps[step].error = None
                # 更新剧本修改时间
                proj.update_script_mtime()
            logger.info(f"项目已加载: {project_dir}")
        else:
            raise FileNotFoundError(f"项目状态文件不存在: {proj.state_file}")
        return proj

    @classmethod
    def load_or_create(
        cls,
        project_root: str,
        name: str,
        script_path: str,
    ) -> "Project":
        """加载已有项目或创建新项目"""
        safe_name = "".join(
            c for c in name if c.isalnum() or c in ("-", "_", ".", " ", "（", "）")
        ).strip()
        project_dir = os.path.join(project_root, safe_name)

        if os.path.exists(os.path.join(project_dir, "state.json")):
            return cls.load(project_dir, script_path)
        else:
            return cls.create(project_root, name, script_path)

    # ========== 目录路径 ==========

    def get_step_dir(self, step: str) -> str:
        """获取步骤输出目录"""
        subdir = STEP_DIRS.get(step, step)
        path = os.path.join(self.project_dir, subdir)
        os.makedirs(path, exist_ok=True)
        return path

    def get_episode_dir(self, step: str, episode_num: int) -> str:
        """获取特定集数的输出目录（分镜/视频用）"""
        step_dir = self.get_step_dir(step)
        ep_dir = os.path.join(step_dir, f"{episode_num:02d}")
        os.makedirs(ep_dir, exist_ok=True)
        return ep_dir

    def get_asset_dir(self, asset_type: str = "character") -> str:
        """获取资产目录"""
        path = os.path.join(self.get_step_dir("asset"), asset_type)
        os.makedirs(path, exist_ok=True)
        return path

    # ========== 状态管理 ==========

    def mark_step_running(self, step: str):
        """标记步骤为运行中"""
        self.state.steps[step].status = "running"
        self.state.steps[step].started_at = datetime.now().isoformat()
        self.state.steps[step].error = None
        self._save_state()
        self.manifest.set_step(step, "running")
        self.manifest.save()

    def mark_step_completed(self, step: str, output_count: int = 0,
                            metadata: Optional[Dict] = None):
        """标记步骤为已完成"""
        self.state.steps[step].status = "completed"
        self.state.steps[step].completed_at = datetime.now().isoformat()
        self.state.steps[step].output_count = output_count
        if metadata:
            self.state.steps[step].metadata.update(metadata)
        self._save_state()
        self.manifest.set_step(step, "completed", output_count=output_count, metadata=metadata or {})
        self.manifest.save()

    def mark_step_failed(self, step: str, error: str):
        """标记步骤为失败"""
        self.state.steps[step].status = "failed"
        self.state.steps[step].completed_at = datetime.now().isoformat()
        self.state.steps[step].error = error
        self._save_state()
        self.manifest.set_step(step, "failed", error=error)
        self.manifest.save()

    def set_artifact(
        self,
        episode_id: str,
        step: str,
        status: str,
        input_hash: str = "",
        config_hash: str = "",
        output_path: str = "",
        error: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist one episode artifact without changing legacy callers."""
        self.manifest.set(str(episode_id), step, ArtifactRecord(
            status=status,
            input_hash=input_hash,
            config_hash=config_hash,
            output_path=output_path,
            error=error,
            metadata=metadata or {},
        ))
        self.manifest.save()

    def mark_stale(self, episode_id: str, from_step: str) -> List[str]:
        """Mark an episode and all dependent outputs stale, retaining files."""
        changed = self.manifest.mark_stale(str(episode_id), from_step)
        if changed:
            for step in changed:
                if step in self.state.steps and self.state.steps[step].status == "completed":
                    self.state.steps[step].status = "stale"
            self._save_state()
            self.manifest.save()
        return changed

    def sync_episode_hashes(self, hashes: Dict[str, str]) -> Dict[str, List[str]]:
        """Update screenplay fingerprints and propagate stale state."""
        changed = self.manifest.sync_episode_hashes(hashes)
        self.manifest.save()
        if changed:
            for step in ("draft",):
                if step in self.state.steps and self.state.steps[step].status == "completed":
                    self.state.steps[step].status = "stale"
            self._save_state()
        return changed

    def is_step_completed(self, step: str) -> bool:
        """检查步骤是否已完成"""
        return self.state.steps.get(step, StepState()).status == "completed"

    def get_step_status(self, step: str) -> str:
        """获取步骤状态"""
        return self.state.steps.get(step, StepState()).status

    def get_completed_steps(self) -> List[str]:
        """获取所有已完成的步骤"""
        return [s for s in STEPS if self.is_step_completed(s)]

    def get_pending_steps(self) -> List[str]:
        """获取所有待执行的步骤"""
        return [
            s for s in STEPS
            if self.state.steps.get(s, StepState()).status in (
                "pending", "failed", "running", "cancelled", "stale", "review"
            )
        ]

    def get_status_summary(self) -> Dict[str, str]:
        """获取所有步骤状态摘要"""
        return {step: self.get_step_status(step) for step in STEPS}

    def web_steps(self) -> Dict[str, Dict[str, Any]]:
        """Return the Web workflow status view, migrating legacy projects on read."""
        return migrate_legacy_state(self.project_dir)

    # ========== 内部方法 ==========

    def _ensure_dirs(self):
        """创建项目目录结构"""
        os.makedirs(self.project_dir, exist_ok=True)
        os.makedirs(os.path.join(self.project_dir, "source"), exist_ok=True)
        os.makedirs(os.path.join(self.project_dir, "analysis", "episodes"), exist_ok=True)
        for step_dir in STEP_DIRS.values():
            os.makedirs(os.path.join(self.project_dir, step_dir), exist_ok=True)
        # 资产子目录
        os.makedirs(os.path.join(self.project_dir, "assets", "character"), exist_ok=True)
        os.makedirs(os.path.join(self.project_dir, "assets", "scene"), exist_ok=True)
        os.makedirs(os.path.join(self.project_dir, "assets", "prop"), exist_ok=True)

    def _save_state(self):
        """保存状态到 state.json"""
        self.state.updated_at = datetime.now().isoformat()

        data = {
            "name": self.state.name,
            "script_path": self.state.script_path,
            "script_mtime": self.state.script_mtime,
            "created_at": self.state.created_at,
            "updated_at": self.state.updated_at,
            "episode_count": self.state.episode_count,
            "steps": {},
        }
        for step_name, step_state in self.state.steps.items():
            data["steps"][step_name] = {
                "status": step_state.status,
                "started_at": step_state.started_at,
                "completed_at": step_state.completed_at,
                "error": step_state.error,
                "output_count": step_state.output_count,
                "metadata": step_state.metadata,
            }

        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False,
            dir=os.path.dirname(self.state_file), suffix=".tmp",
        ) as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path = f.name
        os.replace(temp_path, self.state_file)

    def _load_state(self):
        """从 state.json 加载状态"""
        if not os.path.exists(self.state_file):
            return
        with open(self.state_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.state.name = data.get("name", "")
        self.state.script_path = data.get("script_path", "")
        self.state.script_mtime = data.get("script_mtime", 0.0)
        self.state.created_at = data.get("created_at", "")
        self.state.updated_at = data.get("updated_at", "")
        self.state.episode_count = data.get("episode_count", 0)

        steps_data = data.get("steps", {})
        for step_name, step_data in steps_data.items():
            if step_name not in STEPS:
                continue
            self.state.steps[step_name] = StepState(
                status=step_data.get("status", "pending"),
                started_at=step_data.get("started_at"),
                completed_at=step_data.get("completed_at"),
                error=step_data.get("error"),
                output_count=step_data.get("output_count", 0),
                metadata=step_data.get("metadata", {}),
            )

        # 确保所有步骤都有状态
        for step in STEPS:
            if step not in self.state.steps:
                self.state.steps[step] = StepState()

    def is_script_updated(self) -> bool:
        """检查剧本文件是否已更新"""
        if not os.path.exists(self.state.script_path):
            return False

        current_mtime = os.path.getmtime(self.state.script_path)
        return abs(current_mtime - self.state.script_mtime) > 1.0  # 允许1秒误差

    def update_script_mtime(self):
        """更新剧本文件的修改时间"""
        if os.path.exists(self.state.script_path):
            self.state.script_mtime = os.path.getmtime(self.state.script_path)
            self._save_state()
