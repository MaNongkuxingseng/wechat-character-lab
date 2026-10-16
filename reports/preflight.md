# P0 微信聊天画像项目环境与数据审计

审计日期：2026-10-15（Asia/Shanghai）
范围：仅环境、工程、导出数据与工具审计；未执行画像分析、模型安装或外发上传。

## 1. 已确认事实

### 工作区与 Git

- 工作区：`G:\codex\wechat-character-lab`。
- 顶层包含 `backend/`、`frontend/`、`scripts/`、`data/`、`docs/`；现有转换器为 `scripts/convert_wechatauto_export.py`。
- 通过 `D:\Program Files\Git\cmd\git.exe status --short` 检查，审计开始时工作区无未提交修改；未覆盖或移动用户文件。
- `.gitignore` 已忽略 `data/**`、数据库、音频和 `wechatauto_logs/`；原始聊天、音频和身份信息未写入本报告。

### 导出数据格式与样本统计

- 现有原始导出：`data/inbox/<redacted-single-session>.json`（真实路径已在本机只读核对），为单会话 JSON 对象，包含 `wxid`、`nick_name`、`exported_at`、`chats`、`messages` 字段。
- `messages` 共 37,769 条；记录含 `local_id`、`server_id`、`create_time`、`type_code`、`content`、`sender_name` 等字段。不是 TXT 假设，也不是已验证的 WeChatBridge 私有 API 格式。
- 脱敏类型统计：文本 `type_code=1` 32,718 条；图片 `47` 1,760 条；视频 `43` 78 条；语音 `34` 5 条；其余为系统/链接/附件等类型。
- 视频代表性记录仅保留非内容字段：`type_code=43`，示例 `local_id/server_id/create_time/md5` 存在；原文、联系人和完整标识不写入公开报告。
- 当前项目 `data/` 未发现 `.mp4/.mov/.mkv/.avi/.m4v/.3gp` 视频文件。现有音频清单是 5 个 SILK（总 101,164 bytes；仅记录数量与大小），与视频无关。

### wechatauto-replica 视频导出尝试

- GitHub 检索到候选官方仓库：`fanyuantaier/wechatauto-replica`，Apache-2.0；其作用是 Windows 微信自动化/本地读取与发送，不等同于当前项目已有 JSON 导出文件。
- 在本机 `G:\codex`、用户目录和常见工具目录中未发现名为 `wechatauto-replica` 或其可执行副本；工作区也只有转换器，没有该工具源码或视频导出命令。
- 因此本轮不能安全执行“直接使用 wechatauto-replica 导出视频”：缺少已安装工具、微信运行态/登录会话和可确认的导出 API。未下载、安装、登录、上传或修改微信数据。
- 结论：78 条视频消息已在聊天索引中确认，但本地视频附件尚未关联；不能把“data 无视频”解释为“聊天无视频”。下一步需用户明确提供本地 wechatauto-replica 工作区/运行环境，并先用单条视频小样本验证导出路径。

## 2. 环境审计

- 当前进程 PATH 中未找到：`python`、`python3`、`uv`、`node`、`git`、`ffmpeg`、`ffprobe`、`nvidia-smi`；`pnpm` 命令入口存在但未作为本轮安装动作使用。
- 项目已有虚拟环境：`backend/.venv/`，含 `python.exe`、`pytest.exe`、`uvicorn.exe`、`ruff.exe` 和 `av` 包；本轮不改解释器、不升级 Python、不重装依赖。
- Git 实体位于 `D:\Program Files\Git\cmd\git.exe`，可用完整路径执行；PATH 缺失属于终端进程环境问题。
- 系统 PATH 与常见系统路径均未发现 FFmpeg/FFprobe；项目已有 PyAV 作为本地媒体分析候选，但无视频素材可供提取验证。
- `nvidia-smi` 未在 PATH 或 `C:\Windows\System32\nvidia-smi.exe` 找到；GPU/驱动状态本轮无法确认。未安装、更新或修改驱动/CUDA。

## 3. Chat2Profile、ChatAnalysis.SKILL、GPT-SoVITS

### Chat2Profile

- GitHub 候选：`shuweiran/chat2profile`（README 描述为将聊天历史转为偏好、记忆、性格和礼物洞察）。
- 本轮仅做仓库检索，未克隆、安装或发送聊天数据；许可证与当前版本兼容性尚待逐文件核验。

### ChatAnalysis.SKILL

- GitHub 候选：`JularDepick/ChatAnalysis.SKILL`（README 描述为将聊天记录生成统计报告、人物画像、主题拆解和 HTML 页面）。
- 名称包含 `.SKILL` 不代表可直接作为 Codex Skill。需先确认是否存在符合 Codex 技能约定的 `SKILL.md`、工具权限、输入输出边界与许可证。
- 最小适配方案（不修改第三方原文件）：在本项目建立独立适配层，读取已批准/脱敏的小样本，调用其明确 CLI/脚本；将结果转换为本项目带证据的中间格式；对每个结论保留消息引用、置信度和“观察/推断”标记。若无 `SKILL.md` 或 CLI，则仅作为参考代码，不注册为 Skill。

### GPT-SoVITS

- GitHub 候选：`RVC-Boss/GPT-SoVITS`，公开仓库；项目目标是训练/推理语音合成模型，依赖通常包含独立 Python、PyTorch、CUDA/显卡及较大模型权重。
- 本轮未安装模型、未下载权重、未处理真人声音；许可证、具体 README 版本与硬件矩阵应在用户确认后单独核验。
- 现有 Python 3.14 环境不应强行安装语音依赖；建议为 GPT-SoVITS 单独准备受其 README 支持的 Python 版本和隔离环境，不改当前后端环境。

## 4. 风险与待确认事项

- 视频导出依赖微信桌面运行态、登录权限、目标聊天和工具具体 API；自动猜路径可能读取或导出错误数据，故本轮停止在工具存在性审计。
- 78 条视频消息只有索引证据，没有本地附件字节；不能据此推断可播放时长、内容或发送者身份。
- GitHub 检索结果只确认仓库候选和部分仓库元数据，不能替代逐版本 README/LICENSE 审核。
- 未检测到 GPU/驱动命令，不能判断 GPT-SoVITS 是否具备本机推理条件。

## 5. 下一阶段（等待确认，不自动执行）

1. 用户提供或确认本机已安装的 wechatauto-replica 路径、版本、微信运行状态及允许导出的单条视频消息范围。
2. 仅用一条视频做导出试验，输出到独立的 `data/processed/video_export/`（不覆盖原始数据），记录文件哈希、工具版本、消息索引关联和失败原因。
3. 在不触碰聊天正文的前提下，逐文件核验 Chat2Profile、ChatAnalysis.SKILL、GPT-SoVITS 的 README、LICENSE、Python/显卡兼容性。
4. 若继续语音路线，建立独立 Python 环境并先做小样本、授权检查；不自动安装大型模型或真人声音克隆组件。
5. P0 完成后等待用户确认，再进入 P1；本报告不授权自动开始画像分析。

## 审计执行记录（脱敏）

- 读取项目目录、Git 状态、现有计划/进度文件。
- 统计原始 JSON 消息类型与视频消息数量，不输出聊天正文。
- 检查本地 data 视频文件、现有 SILK 清单、转换脚本和 .gitignore。
- 检查 PATH、项目虚拟环境、Git、FFmpeg、nvidia-smi 可用性。
- 通过 GitHub API 做仓库候选检索；未克隆第三方仓库，未上传本地数据。
