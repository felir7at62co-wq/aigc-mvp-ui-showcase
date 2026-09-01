# Phase 0+1: Dify Fork + First Skill (ScriptSplit)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fork Dify, copy existing AIGC agents into its structure, implement ScriptSplitAdapter, and get the first Skill node working end-to-end on the Dify canvas.

**Architecture:** Dify's Flask backend + React Flow frontend. Existing agents/ copied unchanged. Adapter layer translates Dify Tool parameters into agent parameters. ScriptSplit is the first implementation — proves the pattern before rolling out the remaining 7 Skills.

**Tech Stack:** Dify (MIT) fork, Python 3.10+, Flask, Celery, PostgreSQL, React Flow, MinIO

**Plan Coverage:** Phase 0 (baseline lock) + Phase 1a+b (first Skill + providers), ~3 weeks

**Prerequisites:** Docker, Python 3.10+, Node.js 18+, `dify-main/` cloned at `C:\Users\EDY\Desktop\aigc-mvp-ui\dify-main`

---

## File Structure

```
dify-main/  (Dify fork root)
├── api/core/aigc_skills/                     [NEW]
│   ├── __init__.py
│   ├── base_adapter.py                       SkillAdapter base class
│   ├── skill_registry.py                     Registers all adapters
│   ├── error_handler.py                      SelfHealingErrorHandler port
│   ├── adapters/
│   │   └── script_split_adapter.py           First adapter
│   ├── agents/                               [COPY] Existing agents/*.py
│   │   ├── __init__.py
│   │   ├── screenplay_agent.py
│   │   ├── script_processor.py
│   │   └── ... (14 more agent files)
│   └── clients/                              [COPY] API clients
│       ├── __init__.py
│       ├── runninghub_client.py
│       └── seedance_client.py
│
├── api/core/aigc_skills/providers/           [NEW]
│   ├── __init__.py
│   ├── runninghub_provider.py
│   └── seedance_provider.py
│
├── api/models/aigc_project.py                [NEW]
│
├── api/controllers/service_api/aigc_skills.py [NEW]
│
├── api/tasks/aigc_skill_tasks.py             [NEW]
│
├── web/app/components/workflow/nodes/aigc-skills/  [NEW]
│   ├── index.tsx
│   ├── script-skill-node.tsx
│   └── script-skill-config.tsx
│
├── docker/docker-compose.yml                 [MODIFY] Add MinIO
│
└── migrations/versions/
    └── 001_add_aigc_tables.py                [NEW]
```

---

## Tasks

### Task 1: Baseline Lock — Fork Dify + Docker Up

**Files:**
- Create: (git fork, no new files yet)
- Test: `http://localhost:3000` loads Dify UI

- [ ] **Step 1: Fork Dify**

Create a fork of `dify-main/` into project root:

```bash
# Copy Dify to a working fork location
cd /c/Users/EDY/Desktop/aigc-mvp-ui
cp -r dify-main dify-fork
cd dify-fork
git init
git add .
git commit -m "chore: initial fork of Dify $(git -C ../dify-main log --oneline -1)"
```

- [ ] **Step 2: Create develop-aigc branch**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
git checkout -b develop-aigc
```

- [ ] **Step 3: Start Dify with Docker Compose**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork/docker
cp .env.example .env
docker compose up -d
```

Expected output: Containers starting (api, worker, web, db, redis, nginx).

- [ ] **Step 4: Verify Dify is running**

```bash
# Wait for services to be healthy
docker compose ps
# Check web UI
curl -s http://localhost:3000 | head -5
```

Expected: HTML response with Dify title. Login page at `http://localhost:3000`.

- [ ] **Step 5: Run Dify's existing test suite**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork/api
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -x --tb=short
```

Expected: All tests pass. Record output: `pytest results > ../../docs/superpowers/plans/dify-baseline-test-results.txt`.

- [ ] **Step 6: Commit baseline**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
git add .
git commit -m "chore: baseline Dify fork with passing tests"
```

- [ ] **Step 7: Tag the baseline for reference**

```bash
git tag baseline-dify-v1.2
```

---

### Task 2: Copy Existing Agents into Dify Fork

**Files:**
- Copy: `agents/*.py` → `dify-fork/api/core/aigc_skills/agents/`
- Copy: `core/runninghub_client.py` → `dify-fork/api/core/aigc_skills/clients/`
- Copy: `core/seedance_client.py` → `dify-fork/api/core/aigc_skills/clients/`

- [ ] **Step 1: Create aigc_skills directory structure**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork/api/core
mkdir -p aigc_skills/agents aigc_skills/adapters aigc_skills/clients aigc_skills/providers
touch aigc_skills/__init__.py aigc_skills/agents/__init__.py
touch aigc_skills/adapters/__init__.py aigc_skills/clients/__init__.py
touch aigc_skills/providers/__init__.py
```

- [ ] **Step 2: Copy all agent files**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui
# Copy all .py files from agents/ (16 files, ~6,500 lines)
cp agents/*.py dify-fork/api/core/aigc_skills/agents/
# Verify count
ls dify-fork/api/core/aigc_skills/agents/*.py | wc -l
```

Expected: 16 .py files copied (including `__init__.py`).

- [ ] **Step 3: Copy API clients**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui
cp core/runninghub_client.py core/seedance_client.py dify-fork/api/core/aigc_skills/clients/
```

Expected: `runninghub_client.py` (660 lines) + `seedance_client.py` (235 lines) copied.

- [ ] **Step 4: Verify imports work**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
python -c "
import sys
sys.path.insert(0, 'api')
from api.core.aigc_skills.agents.screenplay_agent import ScreenplayAgent
from api.core.aigc_skills.agents.script_processor import read_script
from api.core.aigc_skills.clients.runninghub_client import RunningHubClient
print('All agents import OK')
"
```

Expected: "All agents import OK" with no errors.

- [ ] **Step 5: Commit**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
git add api/core/aigc_skills/
git commit -m "feat: add existing AIGC agents as copied Layer 3 code"
```

---

### Task 3: Install Dify Python Dependencies + Test Import

- [ ] **Step 1: Install Dify API requirements**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork/api
pip install -r requirements.txt
```

Expected: All dependencies install cleanly.

- [ ] **Step 2: Verify the agents can be imported with Dify's dependencies**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork/api
python -c "
from core.aigc_skills.agents.screenplay_agent import ScreenplayAgent
from core.aigc_skills.agents.audio_generator import AudioGenerator
from core.aigc_skills.agents.asset_generator import AssetGenerator
from core.aigc_skills.agents.prompt_generator import PromptGenerator
from core.aigc_skills.agents.storyboard_generator import StoryboardGenerator
from core.aigc_skills.agents.web_video_generator import SeedanceVideoGenerator
from core.aigc_skills.agents.video_sorter import VideoSorterAgent
from core.aigc_skills.agents.draft_generator import DraftGenerator
from core.aigc_skills.clients.runninghub_client import RunningHubClient
from core.aigc_skills.clients.seedance_client import SeedanceClient
print('All 10 agents/clients import OK')
"
```

Expected: No import errors. If errors occur (e.g., `from core.paths import ...`), those are expected — the old `core/paths.py` will be replaced by Dify's config system. Note them but don't fix yet (the adapters will handle them).

---

### Task 4: Write SkillAdapter Base Class

**Files:**
- Create: `dify-fork/api/core/aigc_skills/base_adapter.py`

- [ ] **Step 1: Write base_adapter.py**

```python
"""
Base class for all AIGC Skill Adapters.
Layer 2: translates between Dify Tool params and Layer 3 (existing agents).

Usage:
    class ScriptSplitAdapter(SkillAdapter):
        skill_name = "script_split"
        agent_class = ScreenplayAgent

        def invoke(self, params: dict) -> dict:
            # Translate Dify params -> agent params
            # Call agent
            # Translate agent result -> Dify result format
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SkillResult:
    success: bool
    output: dict[str, Any] = None
    error: Optional[str] = None
    progress_pct: float = 0.0


class SkillAdapter(ABC):
    """Base adapter. Subclass per Skill."""

    skill_name: str = ""
    skill_label: str = ""
    skill_icon: str = "🧩"
    skill_color: str = "#667eea"

    def __init__(self, config: dict[str, Any] = None):
        self.config = config or {}

    @abstractmethod
    def invoke(self, params: dict[str, Any]) -> SkillResult:
        """Main entry point. Called by Dify Tool node runtime."""
        ...

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Return list of missing/invalid param names."""
        return []

    def get_progress(self, task_id: str) -> float:
        """Optional: poll progress for long-running tasks."""
        return 0.0
```

- [ ] **Step 2: Verify import**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork/api
python -c "from core.aigc_skills.base_adapter import SkillAdapter, SkillResult; print('base_adapter OK')"
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
git add api/core/aigc_skills/base_adapter.py
git commit -m "feat: SkillAdapter base class"
```

---

### Task 5: Write ScriptSplitAdapter

**Files:**
- Create: `dify-fork/api/core/aigc_skills/adapters/script_split_adapter.py`

- [ ] **Step 1: Write ScriptSplitAdapter**

```python
"""
ScriptSplit Skil Adapter.
Input: script file (uploaded to Dify, path in params)
Output: episodes[] (saved to MinIO, file refs in output)
Calls: agents/screenplay_agent.py + agents/script_processor.py
"""
import os
import json
import logging
from typing import Any

from core.aigc_skills.base_adapter import SkillAdapter, SkillResult
from core.aigc_skills.agents.screenplay_agent import ScreenplayAgent, SplitPromptBuilder
from core.aigc_skills.agents.script_processor import read_script

logger = logging.getLogger(__name__)


class ScriptSplitAdapter(SkillAdapter):
    skill_name = "script_split"
    skill_label = "📜 ScriptSplit"
    skill_icon = "📜"
    skill_color = "#667eea"

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config)
        self._llm_client = None

    def invoke(self, params: dict[str, Any]) -> SkillResult:
        script_path = params.get("script_path", "")
        if not script_path or not os.path.exists(script_path):
            return SkillResult(success=False, error="script_path is required and must exist")

        try:
            logger.info(f"ScriptSplit: reading {script_path}")
            script_data = read_script(script_path)
            screenplay_text = script_data["text"]
            logger.info(f"ScriptSplit: {len(screenplay_text)} chars read")
        except Exception as e:
            return SkillResult(success=False, error=f"read_script failed: {e}")

        # Build LLM agent
        llm_client = self._get_llm_client()
        prompt_builder = SplitPromptBuilder.from_file(
            self.config.get("split_template_path", "prompts/default_split_prompt.txt")
        )
        agent = ScreenplayAgent(llm_client=llm_client, prompt_builder=prompt_builder)

        try:
            result = agent.process(screenplay_text)
        except Exception as e:
            return SkillResult(success=False, error=f"ScreenplayAgent.process failed: {e}")

        if not result.get("success"):
            return SkillResult(success=False, error=result.get("error", "unknown agent error"))

        episodes = result.get("episodes", [])
        output_dir = params.get("output_dir", "/tmp/script_split_output")
        os.makedirs(output_dir, exist_ok=True)

        saved = []
        for ep in episodes:
            num = ep["episode_number"]
            content = ep["content"]
            fpath = os.path.join(output_dir, f"{num}.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            saved.append({"number": num, "path": fpath, "char_count": len(content)})

        return SkillResult(
            success=True,
            output={
                "episodes": saved,
                "episode_count": len(saved),
                "total_chars": len(screenplay_text),
            },
            progress_pct=100.0,
        )

    def _get_llm_client(self):
        """Create LLM client from Dify's model config or fallback to env vars."""
        if self._llm_client:
            return self._llm_client
        # Phase 1: use simple env-based config
        # Phase 2: switch to Dify's ModelProvider
        from core.aigc_skills.clients.llm_client_proxy import LLMClientProxy
        self._llm_client = LLMClientProxy.from_config(self.config)
        return self._llm_client
```

- [ ] **Step 2: Write LLM client proxy (adapts old llm_client to Dify config)**

Create `dify-fork/api/core/aigc_skills/clients/llm_client_proxy.py`:

```python
"""
Proxy for existing LLMClient. In Phase 1, reads config from env/dify config.
In Phase 2+, will be replaced by Dify's native ModelProvider.

For now, wraps the existing core.llm_client.LLMClient with the same interface.
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LLMClientProxy:
    """Minimal proxy that creates the existing LLMClient from available config."""

    def __init__(self, api_key: str, base_url: str, model: str,
                 max_tokens: int = 64000, temperature: float = 0.7):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = None

    @classmethod
    def from_config(cls, config: dict) -> "LLMClientProxy":
        return cls(
            api_key=config.get("llm_api_key", os.getenv("LLM_API_KEY", "")),
            base_url=config.get("llm_base_url", os.getenv("LLM_BASE_URL",
                "https://ark.cn-beijing.volces.com/api/coding/v3")),
            model=config.get("llm_model", os.getenv("LLM_MODEL",
                "doubao-seed-2.0-code")),
            max_tokens=int(config.get("llm_max_tokens", os.getenv("LLM_MAX_TOKENS", "64000"))),
            temperature=float(config.get("llm_temperature", os.getenv("LLM_TEMPERATURE", "0.7"))),
        )

    def get_client(self):
        if self._client is None:
            from core.llm_client import LLMClient
            self._client = LLMClient(
                api_key=self.api_key,
                base_url=self.base_url,
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        return self._client

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        client = self.get_client()
        # Adapt to whatever interface the existing LLMClient has
        return client.generate(prompt, system_prompt=system_prompt)
```

Wait — the existing `core.llm_client.py` is at `aigc-mvp-ui/core/llm_client.py`, not inside the Dify fork. The LLMClientProxy needs to import it. Let me adjust:

The existing `core/llm_client.py` depends on `core.config` and `core.paths` which won't exist in the Dify fork. So we have two choices:

A) Copy the LLM client into the agents/clients directory and strip its config dependencies
B) Write a standalone proxy that doesn't depend on the old config

Let's go with a standalone proxy that reads env vars directly — cleaner and avoids dragging in old dependencies:

```python
"""
Proxy for existing LLMClient. Standalone — no dependency on old core/.
Reads config from env vars (Dify's .env or docker-compose env).

In Phase 2+: replace with Dify's native ModelProvider.
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LLMClientProxy:
    """Creates the existing LLMClient from env vars directly."""

    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL",
            "https://ark.cn-beijing.volces.com/api/coding/v3")
        self.model = os.getenv("LLM_MODEL", "doubao-seed-2.0-code")
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "64000"))
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        self._client = None

    def get_client(self):
        if self._client is None:
            # Lazy import: agents may need LLMClient constructor
            from core.llm_client import LLMClient
            self._client = LLMClient(
                api_key=self.api_key,
                base_url=self.base_url,
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        return self._client

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return self.get_client().generate(prompt, system_prompt=system_prompt)

    def generate_with_images(self, prompt: str, image_paths: list[str],
                             system_prompt: str = "", max_tokens: int = 300) -> str:
        return self.get_client().generate_with_images(
            prompt, image_paths, system_prompt=system_prompt, max_tokens=max_tokens
        )
```

- [ ] **Step 3: Verify the adapter imports**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork/api
python -c "
from core.aigc_skills.adapters.script_split_adapter import ScriptSplitAdapter
from core.aigc_skills.clients.llm_client_proxy import LLMClientProxy
print('ScriptSplitAdapter + LLMClientProxy import OK')
"
```

Expected: "ScriptSplitAdapter + LLMClientProxy import OK"

- [ ] **Step 4: Commit**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
git add api/core/aigc_skills/adapters/ api/core/aigc_skills/clients/llm_client_proxy.py
git commit -m "feat: ScriptSplitAdapter + LLMClientProxy"
```

---

### Task 6: Register ScriptSplit as a Dify Tool

**Files:**
- Create: `dify-fork/api/core/aigc_skills/providers/aigc_provider.py`

- [ ] **Step 1: Study Dify's BuiltinToolProvider pattern**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
# Check an example builtin tool provider for reference
cat api/core/tools/builtin_tool/providers/_positions.py | head -30
ls api/core/tools/builtin_tool/providers/ | head -10
```

- [ ] **Step 2: Create AIGC Tool Provider**

Create `dify-fork/api/core/aigc_skills/providers/aigc_provider.py`:

```python
"""
AIGC Skill Tool Provider — registers all AIGC Skill nodes as Dify tools.
"""
from typing import Any
from core.tools.__base.tool_provider import ToolProviderController
from core.tools.__base.tool import Tool
from core.tools.entities.tool_entities import ToolProviderEntity, ToolProviderType
from core.entities.provider_entities import ProviderConfig


class AIGCSkillProvider(ToolProviderController):
    """Registers all AIGC Skill adapters as Dify tools."""

    def __init__(self):
        # Build entity with credentials schema for LLM API
        entity = ToolProviderEntity(
            identity=aigc_provider_identity(),
            credentials_schema=aigc_credentials_schema(),
        )
        super().__init__(entity)

    def get_tool(self, tool_name: str) -> Tool:
        """Return the requested AIGC Skill tool by name."""
        from core.aigc_skills.skill_registry import get_adapter
        adapter_cls = get_adapter(tool_name)
        if adapter_cls is None:
            raise ValueError(f"Unknown AIGC Skill: {tool_name}")
        return AIGCSkillTool(adapter_cls, self)

    @property
    def provider_type(self) -> ToolProviderType:
        return ToolProviderType.BUILT_IN


# --- Helper functions ---

def aigc_provider_identity() -> dict:
    return {
        "title": {"en_US": "AIGC Skills", "zh_Hans": "AIGC 技能"},
        "description": {"en_US": "AIGC video production Skills", "zh_Hans": "AIGC 视频生产技能"},
        "icon": "🎬",
    }


def aigc_credentials_schema() -> list:
    return [
        ProviderConfig(name="llm_api_key", type="text", required=True,
                       label={"en_US": "LLM API Key"}),
        ProviderConfig(name="llm_base_url", type="text", required=False,
                       label={"en_US": "LLM Base URL"}),
        ProviderConfig(name="llm_model", type="text", required=False,
                       label={"en_US": "LLM Model"}),
    ]
```

- [ ] **Step 3: Create AIGCSkillTool wrapper**

Create `dify-fork/api/core/aigc_skills/providers/aigc_tool.py`:

```python
"""
Generic Dify Tool wrapper for AIGC Skill adapters.
Each adapter is wrapped into a Dify-compatible Tool that appears on the canvas.
"""
from collections.abc import Generator
from typing import Any
from core.tools.__base.tool import Tool
from core.tools.entities.tool_entities import ToolInvokeMessage


class AIGCSkillTool(Tool):
    """Wraps a SkillAdapter as a Dify Tool for the workflow canvas."""

    def __init__(self, adapter_cls, provider):
        self._adapter_cls = adapter_cls
        self._adapter = None
        super().__init__(provider=provider)

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        adapter = self._get_adapter()
        result = adapter.invoke(tool_parameters)
        if result.success:
            yield self.create_json_message(result.output)
        else:
            yield self.create_json_message({"error": result.error})

    def _get_adapter(self):
        if self._adapter is None:
            self._adapter = self._adapter_cls()
        return self._adapter

    def get_runtime(self) -> dict:
        return {}
```

- [ ] **Step 4: Create skill_registry.py**

Create `dify-fork/api/core/aigc_skills/skill_registry.py`:

```python
"""
Central registry mapping skill names to their adapter classes.
"""
from typing import Optional


_registry = {}


def register_skill(name: str, adapter_cls):
    _registry[name] = adapter_cls


def get_adapter(name: str):
    return _registry.get(name)


def list_skills():
    return list(_registry.keys())
```

- [ ] **Step 5: Register ScriptSplit in the registry**

Append to `dify-fork/api/core/aigc_skills/__init__.py`:

```python
from core.aigc_skills.skill_registry import register_skill
from core.aigc_skills.adapters.script_split_adapter import ScriptSplitAdapter

register_skill("script_split", ScriptSplitAdapter)
```

- [ ] **Step 6: Verify all imports**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork/api
python -c "
from core.aigc_skills import list_skills
from core.aigc_skills.skill_registry import get_adapter
from core.aigc_skills.providers.aigc_provider import AIGCSkillProvider
from core.aigc_skills.providers.aigc_tool import AIGCSkillTool
print('Registered skills:', list_skills())
print('All provider imports OK')
"
```

Expected: "Registered skills: ['script_split']" + no import errors.

- [ ] **Step 7: Commit**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
git add api/core/aigc_skills/__init__.py
git add api/core/aigc_skills/skill_registry.py
git add api/core/aigc_skills/providers/
git commit -m "feat: AIGC Skill provider registry + Dify Tool wrapper"
```

---

### Task 7: Create AIGC Project Database Model

**Files:**
- Create: `dify-fork/api/models/aigc_project.py`
- Create: `dify-fork/migrations/versions/001_add_aigc_tables.py`

- [ ] **Step 1: Write the SQLAlchemy model**

Create `dify-fork/api/models/aigc_project.py`:

```python
"""
AIGC Project and Asset database models.
Extends Dify's existing schema — NOT modifying Dify's core models.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from extensions.ext_database import db


class AigcProject(db.Model):
    __tablename__ = "aigc_projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    script_path = Column(String(500))
    episode_count = Column(Integer, default=0)
    status = Column(String(32), default="draft")  # draft | running | completed | failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))


class AigcStepRun(db.Model):
    __tablename__ = "aigc_step_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("aigc_projects.id"), nullable=False)
    step_name = Column(String(64), nullable=False)
    status = Column(String(32), default="pending")
    output_count = Column(Integer, default=0)
    llm_tokens = Column(Integer, default=0)
    rh_task_count = Column(Integer, default=0)
    error = Column(Text)
    metadata = Column(JSON, default=dict)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class AigcAsset(db.Model):
    __tablename__ = "aigc_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("aigc_projects.id"), nullable=False)
    asset_type = Column(String(32), nullable=False)  # character | scene | prop
    name = Column(String(255), nullable=False)
    description = Column(Text)
    image_url = Column(String(500))
    thumbnail_url = Column(String(500))
    metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 2: Create Alembic migration**

Create `dify-fork/migrations/versions/001_add_aigc_tables.py`:

```python
"""Add AIGC project tables

Revision ID: 001_add_aigc_tables
Revises: (previous Dify migration ID)
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "001_add_aigc_tables"
down_revision = None  # Will be set to Dify's latest migration after fork


def upgrade():
    op.create_table(
        "aigc_projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("script_path", sa.String(500)),
        sa.Column("episode_count", sa.Integer, default=0),
        sa.Column("status", sa.String(32), default="draft"),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
        sa.Column("created_by", UUID(as_uuid=True)),
    )
    op.create_table(
        "aigc_step_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("step_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), default="pending"),
        sa.Column("output_count", sa.Integer, default=0),
        sa.Column("llm_tokens", sa.Integer, default=0),
        sa.Column("rh_task_count", sa.Integer, default=0),
        sa.Column("error", sa.Text),
        sa.Column("metadata", JSON, default=dict),
        sa.Column("started_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime),
    )
    op.create_table(
        "aigc_assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("image_url", sa.String(500)),
        sa.Column("thumbnail_url", sa.String(500)),
        sa.Column("metadata", JSON, default=dict),
        sa.Column("created_at", sa.DateTime),
    )


def downgrade():
    op.drop_table("aigc_assets")
    op.drop_table("aigc_step_runs")
    op.drop_table("aigc_projects")
```

- [ ] **Step 3: Run migration to verify**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork/api
flask db upgrade
```

Expected: Tables created. Check with `psql` or `docker compose exec db psql -U postgres -c "\dt aigc_*"`.

- [ ] **Step 4: Commit**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
git add api/models/aigc_project.py migrations/versions/001_add_aigc_tables.py
git commit -m "feat: AIGC project + step run + asset DB models"
```

---

### Task 8: Create ScriptSplit React Flow Node UI

**Files:**
- Create: `dify-fork/web/app/components/workflow/nodes/aigc-skills/index.tsx`
- Create: `dify-fork/web/app/components/workflow/nodes/aigc-skills/script-skill-node.tsx`
- Create: `dify-fork/web/app/components/workflow/nodes/aigc-skills/script-skill-config.tsx`

- [ ] **Step 1: Study Dify's existing node pattern**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
# Check how an existing node is structured
ls web/app/components/workflow/nodes/llm/
cat web/app/components/workflow/nodes/llm/index.tsx | head -30
```

Expected: Understand the Dify node component pattern (they define `NodeDefault` with `defaultValue`, `checkValid`, and export the component).

- [ ] **Step 2: Create the index with node registration**

Create `dify-fork/web/app/components/workflow/nodes/aigc-skills/index.tsx`:

```typescript
import type { NodeDefault } from '../../types'
import { BlockEnum } from '../../types'

// Register all AIGC Skill nodes here
export const AIGC_SKILL_NODES: Record<string, NodeDefault> = {
  [BlockEnum.TOOL]: {
    defaultValue: {
      tool_name: 'script_split',
      provider_id: 'aigc_skills',
    },
    checkValid: () => ({ isValid: true }),
  },
}
```

- [ ] **Step 3: Create ScriptSplit node component**

Create `dify-fork/web/app/components/workflow/nodes/aigc-skills/script-skill-node.tsx`:

```tsx
import { memo } from 'react'
import type { NodeProps } from '../../types'
import { NodeRunningStatus } from '../../types'

// Reuse Dify's base node rendering (or build simple custom card)
// Phase 1: minimal — just shows name + status + run button
// Phase 2: style like ComfyUI / libTV

const ScriptSkillNode = memo((props: NodeProps) => {
  const { data, selected } = props
  const status = data._runningStatus ?? NodeRunningStatus.Idle

  return (
    <div className={`
      relative rounded-lg border-2 px-4 py-3 min-w-[200px]
      ${selected ? 'border-[#667eea] shadow-lg' : 'border-[#404040]'}
      bg-[#2d2d2d] text-white
    `}>
      {/* Header with gradient */}
      <div className="absolute top-0 left-0 right-0 h-[4px] rounded-t-lg bg-gradient-to-r from-[#667eea] to-[#764ba2]" />

      {/* Title */}
      <div className="flex items-center gap-2 mt-1">
        <span className="text-lg">📜</span>
        <span className="font-bold text-sm">ScriptSplit</span>
      </div>

      {/* Status */}
      <div className="text-xs text-gray-400 mt-1">
        {status === NodeRunningStatus.Idle && '⚪ 待处理'}
        {status === NodeRunningStatus.Running && '🔵 执行中...'}
        {status === NodeRunningStatus.Succeeded && '✅ 已完成'}
        {status === NodeRunningStatus.Failed && '❌ 失败'}
      </div>
    </div>
  )
})

ScriptSkillNode.displayName = 'ScriptSkillNode'
export default ScriptSkillNode
```

- [ ] **Step 4: Register the node in Dify's block selector**

Read the existing block registration to find where to add:

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
grep -n "BlockEnum" web/app/components/workflow/block-selector/blocks.tsx | head -5
grep -n "all-start-blocks" web/app/components/workflow/block-selector/all-start-blocks.tsx | head -5
```

Expected: Find the import/registration pattern. Our Tool-type node should register through the existing tool provider mechanism.

- [ ] **Step 5: Commit**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
git add web/app/components/workflow/nodes/aigc-skills/
git commit -m "feat: ScriptSplit React Flow node UI"
```

---

### Task 9: Agent API Endpoints (Basic)

**Files:**
- Create: `dify-fork/api/controllers/service_api/aigc_skills.py`

- [ ] **Step 1: Create Agent API controller**

```python
"""
Agent API endpoints for executing AIGC Skills.
Uses Dify's existing API Key auth.
"""
from flask import request, jsonify
from flask_login import login_required
from core.aigc_skills.skill_registry import get_adapter, list_skills


def init_aigc_api(app):
    """Register AIGC API routes on the Flask app."""

    @app.route("/api/aigc/skills", methods=["GET"])
    @login_required
    def list_aigc_skills():
        return jsonify({"skills": list_skills()})

    @app.route("/api/aigc/skills/<skill_name>/run", methods=["POST"])
    @login_required
    def run_aigc_skill(skill_name):
        adapter_cls = get_adapter(skill_name)
        if adapter_cls is None:
            return jsonify({"error": f"Unknown skill: {skill_name}"}), 404

        params = request.get_json(silent=True) or {}
        adapter = adapter_cls()
        result = adapter.invoke(params)

        if result.success:
            return jsonify({"success": True, "output": result.output})
        else:
            return jsonify({"success": False, "error": result.error}), 500

    return app
```

- [ ] **Step 2: Register routes in Dify's app factory**

Read the Dify app factory to find where to register blueprints:

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
grep -n "register_blueprint\|register_api\|init_api" api/app_factory.py | head -10
```

Expected: Find the pattern for registering new route groups. If Dify uses Flask blueprints, create one for the AIGC API.

- [ ] **Step 3: Test the API**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
# Start the API server
docker compose up -d api
# Test listing skills
curl -s http://localhost:5001/api/aigc/skills
```

Expected: `{"skills":["script_split"]}`

- [ ] **Step 4: Commit**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
git add api/controllers/service_api/aigc_skills.py
git commit -m "feat: Agent API endpoints for AIGC skills"
```

---

### Task 10: Docker Compose — Add MinIO

- [ ] **Step 1: Add MinIO service to docker-compose.yml**

Read the Dify docker-compose.yml to find where to add the service:

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
cat docker/docker-compose.yml | head -20
```

Then add MinIO:

```yaml
  # Add after the redis service
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-admin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-admin123}
    restart: always

volumes:
  # ... existing volumes ...
  minio_data:
```

- [ ] **Step 2: Verify MinIO starts**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork/docker
docker compose up -d minio
curl -s http://localhost:9000/minio/health/live
```

Expected: `{"status":"alive"}`

- [ ] **Step 3: Commit**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork
git add docker/docker-compose.yml
git commit -m "feat: add MinIO for AIGC asset storage"
```

---

### Task 11: End-to-End Integration Test

- [ ] **Step 1: Write integration test**

Create temporary test script:

```python
"""
Integration test: ScriptSplit end-to-end.
1. Create a test script file
2. Call the adapter directly
3. Verify output episodes
"""
import os
import tempfile
import json

# Create a test script
test_script = """第1集
这是一个测试剧本的第一集内容。
角色A：你好
角色B：你好，有什么可以帮助你的吗？
角色A：我需要测试剧本拆分功能。
旁白：这是一个测试场景。

第2集
角色A：这是第二集。
角色B：是的，我们继续测试。
旁白：测试继续进行中。
"""

with tempfile.TemporaryDirectory() as tmpdir:
    script_path = os.path.join(tmpdir, "test_script.txt")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(test_script)

    output_dir = os.path.join(tmpdir, "output")
    os.makedirs(output_dir, exist_ok=True)

    # Test adapter
    from core.aigc_skills.adapters.script_split_adapter import ScriptSplitAdapter
    adapter = ScriptSplitAdapter()
    result = adapter.invoke({
        "script_path": script_path,
        "output_dir": output_dir,
    })

    print(f"Success: {result.success}")
    if result.success:
        print(f"Episodes: {len(result.output['episodes'])}")
        for ep in result.output['episodes']:
            print(f"  Episode {ep['number']}: {ep['char_count']} chars")
    else:
        print(f"Error: {result.error}")

# Note: This test requires LLM_API_KEY env var and the actual LLM service
# It's an integration test, not a unit test
```

- [ ] **Step 2: Run the test**

```bash
cd /c/Users/EDY/Desktop/aigc-mvp-ui/dify-fork/api
LLM_API_KEY=your_key_here python -c "
# Paste the test script above or save to file
exec(open('../test_script_split.py').read())
"
```

Expected: Success with 2 episodes (or actual LLM-parsed output).

- [ ] **Step 3: Debug and fix any issues**

If the test fails, check common issues:
- LLM API key not configured
- `read_script()` path issues
- Agent import dependency missing (e.g., old `core.paths` references)
- File encoding issues

Fix issues in the adapter or LLMClientProxy as needed.

---

## Milestone: Phase 1 Complete ✅

At this point:
- Dify fork runs at `localhost:3000`
- ScriptSplit adapter registered as a Dify Tool
- ScriptSplit React Flow node appears on the canvas
- Agent API can trigger ScriptSplit via `POST /api/aigc/skills/script_split/run`
- MinIO stores output files
- DB tables created

**Next:** Phase 2 — wrap the remaining 7 Skills as adapters, same pattern as ScriptSplit.
