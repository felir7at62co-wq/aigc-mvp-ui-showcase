# AIGC 短剧视频工作台

当前项目是 Web 版短剧视频生产工作台，流程精简为：

1. 创建项目并导入剧本，后台自动识别分集。
2. 提取角色、场景、道具并使用 GPT Image 2 生成资产图。
3. 生成完整镜头脚本并匹配资产。
4. 使用 Seedance 2.0 按 15 秒子任务直接生成视频。
5. 内置 FFmpeg 按镜头时长切分片段，在同一视频生成页面完成预览、轨道调整和导出。

## 本地启动

后端：

```powershell
python -m web_api.run_server
```

前端：

```powershell
cd web
npm install
npm run dev
```

默认地址：前端 `http://127.0.0.1:5173`，API `http://127.0.0.1:8787`。

## 环境变量

复制 `.env.example` 为 `.env`，在本地填写：

- `YUNYING_API_KEY`：图片与视频生成凭据。
- `YUNYING_BASE_URL`：默认 `https://wy6688.token6688.com/v1`。
- `YUNYING_VIDEO_MODEL`：默认 `seedance-2-0-official`。
- `YUNYING_IMAGE_MODEL`：默认 `gpt-image-2-official`。
- `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`：剧本分析与镜头脚本生成。

真实密钥不得写入源码、`config.yaml` 或提交记录。

## 验证

```powershell
python -m pytest -q --basetemp=.pytest-tmp
cd web
npm test -- --run
npm run build
```
