# AIGC Skill Platform — Design Document

**Date**: 2026-06-10
**Status**: Draft
**Fork Base**: [Dify](https://github.com/langgenius/dify) (MIT License, ⭐50k+)

## 1. Product Vision

**Med Agents for AIGC** — A platform where AI agents (like Claude Code, Codex) and human creators share a unified set of AIGC Skills, visually composed on an infinite canvas.

```
Claude Code / Codex (写代码)  →  本平台 (AIGC Skill 编排)
Agent 技能：linter/compiler    →  Agent 技能：ScriptSplit/AudioGen/VideoGen
输出：代码/PR                 →  输出：分镜/视频/剪映草稿
```

### Core Concept: 节点即 Skill

Every node on the canvas IS a Skill. The same Skill can be:
- **Dragged by humans** on the visual canvas
- **Called by agents** via REST API (`POST /skills/{name}/run`)
- **Composed into workflows** by both

### Target Users

| User | Interface | Priority |
|------|-----------|----------|
| AIGC 创作者 | Web 画布 (Drag & Drop) | MVP |
| Agent 开发者 | REST API + WebSocket | MVP |

## 2. Architecture

### Tech Stack

| Layer | Technology | Source |
|-------|-----------|--------|
| Frontend | Next.js 14+ / TypeScript / React Flow | Dify web/ |
| Backend | Flask + Python 3.10+ | Dify api/ |
| DB | PostgreSQL + Redis | Dify native |
| File Storage | MinIO / S3 | New |
| Task Queue | Celery + Redis | Dify native |
| Deployment | Docker Compose | Dify native |

### Architecture Mapping (Dify → Our Platform)

```
Dify Layer                  Keep         Replace With
─────────────────────────────────────────────────────────
Frontend Canvas (React Flow) ✅           Add AIGC Skill nodes
Workflow Engine (GraphEngine) ✅          Add AIGC executors
User/Team (Tenant/RBAC)     ✅            Extend project sharing
Model Providers (20+ LLMs)  ✅            Add RunningHub/Seedance
Chat/RAG UI                 ❌            AIGC Project Dashboard
LLM/Knowledge Nodes         ❌            8 AIGC Skill nodes
API Layer                   ✅            Add Agent API endpoints
```

### File Structure (Fork Additions)

```
dify/
├── api/core/aigc_skills/           ← Your existing codebase
│   ├── __init__.py
│   ├── base_skill_adapter.py       ← Abstract base for all Skills
│   ├── skill_registry.py           ← Register all 8 Skills
│   ├── engine.py                   ← Original pipeline_engine.py (adapted)
│   ├── adapters/                   ← 8 Skill adapters
│   │   ├── script_split_adapter.py
│   │   ├── audio_gen_adapter.py
│   │   ├── asset_gen_adapter.py
│   │   ├── prompt_gen_adapter.py
│   │   ├── storyboard_adapter.py
│   │   ├── video_gen_adapter.py
│   │   ├── video_sort_adapter.py
│   │   └── draft_export_adapter.py
│   ├── agents/                     ← Your original agents/* (unchanged)
│   │   ├── screenplay_agent.py
│   │   ├── audio_generator.py
│   │   ├── asset_generator.py
│   │   ├── ...
│   └── clients/                    ← Original API clients (adapted)
│       ├── runninghub_client.py
│       └── seedance_client.py
├── api/controllers/service_api/
│   └── aigc_skills.py              ← Agent API endpoints (NEW)
├── api/models/
│   └── aigc_project.py             ← Project/Asset DB models (NEW)
├── api/tasks/
│   └── aigc_skill_tasks.py         ← Celery async tasks (NEW)
├── web/app/components/workflow/nodes/
│   └── aigc-skills/                ← 8 frontend Skill nodes (NEW)
│       ├── script-skill-node.tsx
│       ├── audio-skill-node.tsx
│       ├── asset-skill-node.tsx
│       ├── prompt-skill-node.tsx
│       ├── storyboard-skill-node.tsx
│       ├── video-gen-skill-node.tsx
│       ├── video-sort-skill-node.tsx
│       └── draft-skill-node.tsx
└── docker/
    └── docker-compose.yml          ← Add MinIO, GPU worker
```

## 3. Skill Node Design

### 8 Skills (Layer 3: Your Existing Code)

| Skill | Input | Output | Backend | Source File |
|-------|-------|--------|---------|-------------|
| 📜 ScriptSplit | script file (.txt/.docx) | episodes[] | LLM Agent | agents/screenplay_agent.py |
| 🎵 AudioGen | episode_text, voice_ref | audio_files[] | RunningHub | agents/audio_generator.py |
| 🖼 AssetGen | episode_text | character_descriptions, scene_descriptions | LLM + RunningHub | agents/asset_generator.py |
| 🎬 PromptGen | episode_text | shot_scripts[] | LLM | agents/prompt_generator.py |
| 🎨 Storyboard | shot_scripts, character_refs | storyboard_images[] | RunningHub | agents/storyboard_generator.py |
| 🎥 VideoGen | storyboard_images | video_clips[] | Seedance | agents/web_video_generator.py |
| 📂 VideoSort | video_clips, order_map | sorted_videos[] | Local | agents/video_sorter.py |
| ✂️ DraftExport | audio_files, sorted_videos | 剪映草稿 | Local | agents/draft_generator.py |

### Three-Layer Architecture per Skill

```
Layer 1: Dify Plugin (Tool)       → Input/Output Schema, UI config
Layer 2: Adapter (NEW)            → Translates Dify params → Agent params
Layer 3: Existing Code (UNCHANGED) → agents/*.py, clients/*.py
```

### Execution Flow

```
User/Agent triggers workflow
  → Dify GraphEngine (topological sort)
  → For each node: 
       SkillAdapter.invoke(params)
         → Your agent.process(params)
           → RunningHub/LLM/Seedance
         → Return result
  → WebSocket push progress → Frontend node status update
  → Complete
```

## 4. Agent API Design

```
POST   /skills/{skill_name}/run              # Execute single Skill
POST   /workflows/run                         # Execute full workflow
GET    /workflows/{id}/status                 # Poll execution status
GET    /workflows/{id}/result                 # Get execution result
WS     /workflows/{id}/stream                 # Real-time streaming
GET    /projects                              # List projects
POST   /projects                              # Create project
GET    /projects/{id}/assets                  # List project assets
```

Authentication: Dify's existing API Key system.

## 5. Phased Implementation

### Phase 1: Skeleton (Week 1-2)
- Fork Dify, get docker-compose running
- Create `api/core/aigc_skills/` structure
- Port scripts into adapters/
- Implement first Skill (ScriptSplit) end-to-end
- Test: ScriptSplit node in Dify canvas → run → result

### Phase 2: All 8 Skills (Week 3-5)
- Wrap remaining 7 Skills as Dify Tools
- Frontend: Custom node UI for all 8 Skills
- File storage: MinIO/S3 integration
- Asset Library DB models
- Test: Full pipeline → video output

### Phase 3: Agent API + Team (Week 6-7)
- Agent REST API endpoints
- WebSocket streaming
- Workspace sharing, RBAC
- Test: curl-driven workflow execution + 2-user collaboration

### Phase 4: Marketplace + Launch (Week 8-9)
- Skill marketplace (browse/install/publish)
- Skill SDK + documentation
- Docker production deployment
- Load testing (100 concurrent users)

## 6. Development Principles (Vibe Coding)

1. **Test first** — Run Dify's existing test suite before any modification
2. **Don't break what works** — Don't modify Dify core; only add new modules
3. **Adapter pattern** — Your existing code stays untouched behind adapters
4. **Verify before commit** — Each Phase must pass tests before moving on

## 7. Open Source Projects to Reference

| Project | Stars | Use |
|---------|-------|-----|
| [Dify](https://github.com/langgenius/dify) | 50k+ | Fork base |
| [Ryven](https://github.com/leon-thomm/ryven) | 3.9k | Node item rendering patterns |
| [n8n](https://github.com/n8n-io/n8n) | 65k+ | Workflow execution engine patterns |
| [MachinaOS](https://github.com/zeenie-ai/MachinaOS) | New | Plugin architecture reference |
