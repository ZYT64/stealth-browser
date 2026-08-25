# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup: camera names and locations, SSH hosts and aliases, preferred TTS voices, speaker/room names, device nicknames, anything environment-specific.

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## Summarize CLI（2026-08-10 安装）

- 仓库 steipete/summarize（TypeScript，官方只发 macOS 二进制），树莓派 arm64 源码构建：~/apps/summarize（pnpm build），软链 ~/.local/bin/summarize → dist/cli.js，版本 v0.21.10
- 配置：~/.summarize/config.json（默认模型已设 openrouter/nvidia/nemotron-3-ultra-550b-a55b:free；models.free 含 3 个实测可用候选）；key 在 ~/.bashrc 的 OPENROUTER_API_KEY（OpenRouter sk-or-v1，2026-08-10 用户提供）
- OpenRouter 免费非御三家模型实测（refresh-free 9 个中 3 个可用）：nvidia/nemotron-3-ultra-550b-a55b:free（550B/977k ctx，最快）、poolside/laguna-s-2.1:free、nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free（多模态）
- 大陆可达性：openrouter.ai API 实测 200（约 4.4s）；Google 直连不可达（符合预期）
- 用法：`summarize <url|file|youtube>`，--length short/medium/long/xl/xxl，--model openrouter/...

## GitHub 加速（2026-08-05 部署，arm64 Pi）

- **调优版 GitHub520 hosts**：数据源 https://raw.hellogithub.com/hosts（国内 CDN 秒开），本网络实测调优：raw/.133 域→185.199.108.133、assets .215→185.199.109.215、.153 域→185.199.108.153（GitHub520 默认 111.x 段本网不通）；/etc/hosts 已备份
- 自动更新：systemd user 定时器 `openclaw-github-hosts.timer`（每天 06:30 + 开机 10 分钟），脚本 ~/.openclaw/scripts/github-hosts-update.sh（拉取→校验→调优→替换块→验证），日志 ~/.openclaw/logs/github-hosts-update.log
- **ghdl 加速下载器**：~/.local/bin/ghdl，用法 `ghdl <github-url> [-o 文件]`；自动探测 ghfast.top/ghproxy.net/gh-proxy.com/ghp.ci/ghproxy.cn 选最快，全挂直连兑底
  - ⚠️ 2026-08-11：ghproxy.cn 探测延迟最低会被选中，但大文件返回 HTML 错误页（4.4M 包只下到 6.8K）；遇到明显过小的文件先 `file` 验证，换 gh-proxy.com 直下（实测稳定 ~1MB/s）
- 实测：api 1.35s、raw 200；gitclone.com 镜像 11.3s 反而慢，不用
- **git 全局加速（2026-08-06）**：`url."https://gh-proxy.com/https://github.com/".insteadOf https://github.com/`（fetch/clone 走代理）+ pushInsteadOf 回直连（代理只读）；实测 clone GitHub520 仓库 2.4s vs 直连 71.8s（直连数据面被限速）；注意 release 大文件直连 objects.githubusercontent.com 也常被掐（240s 0 字节），大文件用 ghdl 镜像
- 注意：github.com 主页（首页重资源）仍偏慢属路由拥塞，git/API/raw 已正常；浏览器访问建议搭配镜像站

## OpenClaw Self-Healing（2026-08-05 部署）

- 仓库：Ramsbaby/openclaw-self-healing（克隆源在 /tmp/openclaw-self-healing）
- 脚本目录：`~/.openclaw/skills/openclaw-self-healing/scripts/`（含 lib/notify.sh, lib/llm-gateway.sh），SKILL.md 同目录
- 配置：`~/.openclaw/.env`（chmod 600，端口 18789，告警通道全部留空——国内 Discord/Slack/TG 不可达，告警只写日志）
- 日志/状态：`~/.openclaw/logs/`（watchdog.log、healthcheck-*.log、gateway.err.log）、`~/.openclaw/watchdog/`（崩溃计数、backoff、恢复状态）
- 定时器（user 级 systemd，已 enable + linger 已开）：
  - `openclaw-watchdog.timer` 每 3 分钟 → gateway-watchdog.sh（PID/HTTP/内存检查 + 指数退避重启 + openclaw doctor --fix）
  - `openclaw-healthcheck.timer` 每 5 分钟 → gateway-healthcheck.sh（HTTP 检查 + openclaw gateway restart 重试）
- 已打 Linux 补丁：gateway-watchdog.sh 的 launchctl 逻辑改为 `systemctl --user` 分支（IS_MACOS 开关，macOS 分支保留）；网关服务名 `openclaw-gateway.service`（user 级，端口 18789）
- **Level 3（Claude AI 修复）不可用**：本机无 claude CLI，触发时只记 ERROR 日志；Level 4 告警通道国内不可用，留空
- 查看：`systemctl --user list-timers | grep openclaw`；手动跑：`bash ~/.openclaw/skills/openclaw-self-healing/scripts/gateway-watchdog.sh --dry-run`

## LLM Provider → Claude Code 每日同步（2026-08-05 建，14:33 改版）
- **当前目标（2026-08-13 18:05 用户定）：最强免费组合 free-all**（SYNC_TARGET=omniroute-free-all，base http://127.0.0.1:20128/v1，全角色模型统一 free-all；SKIP_MODEL_CATALOG=True 跳过模型目录拉取；脚本内置 v4-pro 黑名单防进 OpenClaw fallback）

- 脚本：`~/.openclaw/scripts/llm-provider-sync.py`，定时器 `openclaw-llm-sync.timer`（每天 00:00，user systemd，已 enable）
- **Claude 侧同步目标固定 SYNC_TARGET，不跟随 OpenClaw 主模型**（08-21 主模型切 minimax-portal/MiniMax-M3 后核对确认；脚本第 154 行注释明示）
- 逻辑（全部走 cc-switch，不手改配置）：读 OpenClaw 主模型（openclaw.json agents.defaults.model.primary）→ provider baseUrl → **API key 从 agent 库读**（~/.openclaw/agents/main/agent/openclaw-agent.sqlite 的 auth_profile_store 表，deepseek/minimax 凭据都在这）
  - Claude Code 侧：比对/重建 cc-switch 的 claude provider（env: ANTHROPIC_BASE_URL/AUTH_TOKEN/MODEL + 角色模型 ANTHROPIC_DEFAULT_OPUS/SONNET/HAIKU_MODEL），`cc-switch use` 应用，由 cc-switch 写 ~/.claude/settings.json
  - **fallback：Claude 侧=cc-switch 的角色模型（opus 用最高档，sonnet/haiku 用主模型）；OpenClaw 侧=cc-switch config openclaw agents fallback（新模型自动 add，上限 4 个）**
  - 新模型检测：配置目录 + 线上 /models API（带 key），与状态文件 ~/.openclaw/logs/.llm-sync-model-state.json 比对
- DeepSeek 走 https://api.deepseek.com/anthropic 兼容端点（国内可达）；同步日志 ~/.openclaw/logs/llm-sync-*.log
- 技术点：cc-switch provider delete 需要 TTY 确认 → 脚本用 `script -qec` 伪 TTY + 管道 y；每次 cc-switch 运行会把线上 settings.json 自动导入为 default provider（空 env，无害）
- **注意：cc-switch CLI 里没存任何 API key**（providers 表只有空的官方 provider）；OpenClaw 真实凭据在 agent 库 auth_profile_store
- 用户要求：配置 Claude Code 一律先想 cc-switch，能通过 cc-switch 就不自己干（已入 MEMORY.md）

## AI CLI 工具（2026-08-05 安装）

- **cc-switch** v5.10.0：`~/.local/bin/cc-switch`（Rust 二进制，arm64 musl），统一管理 Claude Code/Codex/Gemini/OpenCode/OpenClaw 的 provider 配置、MCP、skills、prompts、代理路由
  - 安装：GitHub release 直连超时 → 走 ghfast.top 镜像下载 cc-switch-cli-linux-arm64-musl.tar.gz
  - 常用：`cc-switch provider list/switch`、`cc-switch use <id>`、`cc-switch config`、`cc-switch skills install`
- **Claude Code CLI** v2.1.222：`~/.nvm/versions/node/v24.19.0/bin/claude`（npm -g @anthropic-ai/claude-code，registry 已是 npmmirror）
  - 注意：postinstall 被 allow-scripts 拦过，已手动 `node install.cjs` 补跑
  - 国内 api.anthropic.com 不可达：未登录/未配 key，需用 cc-switch 配中转 provider（ANTHROPIC_BASE_URL）才能用
  - 自愈系统 Level 3（claude CLI 医生）现在理论上可用了，但需先配好 key

## Agent Mail CLI（2026-08-05 装）

- CLI：`agently-cli` v1.0.13（npm -g @tencent-qqmail/agently-cli），Skill：`~/.openclaw/skills/agently-mail/`（npx skills add https://agent.qq.com 自动装，含 claude 软链）
- 邮箱：kuroneko0804@agent.qq.com（OAuth 已授权，设备码流程：agently-cli auth login → 输出 URL 给用户浏览器授权）
- 常用：`agently-cli +me` 验证；发/收/搜邮件见 SKILL.md；管理端 agent.qq.com

## Microsoft 365 MCP (个人账号)

- Server: `@softeria/ms-365-mcp-server` (全局 npm 安装)，mcporter 配置名 `ms365`
- 配置文件: `~/.openclaw/workspace/config/mcporter.json`，env 设了 `MS365_MCP_TENANT_ID=consumers`（个人账号必须，否则 refresh token 会被拒）
- 账号: Neo Lirael (zyt_everyday@outlook.com)，token 已持久化，无需重复登录
- 用法: `mcporter call ms365.<tool> ...`（从 workspace 目录执行）
  - 邮件: `list-mail-messages` / `get-mail-message` / `create-draft-email` / `send-email`
  - 日历: `list-calendar-events` / `create-calendar-event`（带参时用 `--args '{"key":"value"}'` JSON 方式传参，key:value 方式对部分必填参数会丢）
  - To Do: `list-todo-task-lists` → `list-todo-tasks`（需 todoTaskListId）
- 重登录: `ms-365-mcp-server --login`（设备码流程）
- 若 token 失效：先 `mcporter call ms365.login`，再走设备码

## OmniRoute 上下文压缩配置（2026-08-12 建）
- 目的：CC 用 `opencode/deepseek-v4-flash-free`（走 free-all combo，模型 ctx 200K，opencode provider 默认 defaultContextLength）时，长会话工具输出堆积导致 Claude Code 自带的 compact/重置触发。OmniRoute 在请求**到上游之前**做压缩，让 ctx 涨得更慢。
- 配置现状：全局 ON，**默认 stacked（RTK → Caveman）** + autoTrigger 32K tokens + contextBudget floor + liveZone ON
- 关键开关：
  - `rtk.intensity=standard, applyToToolResults=true` — 工具输出（pytest/git/build/diff）是 CC ctx 膨胀主因
  - `caveman.intensity=full, compressRoles=[user,assistant]` — prose 压缩；SHARED_BOUNDARIES 保护 code/path/URL/stack
  - `liveZone.enabled=true` — 最近几轮不压，保留近期精度
  - `contextBudget.mode=floor, policy=reserve-output, outputReserve=8192, safetyMargin=2048` — 估算 > (200K-8K-2K)≈190K 时沿 ladder 升级压缩直到塞得下，**直接防 ctx 超限触发 CC compact**
  - `autoTriggerTokens=32000` — 短会话不触发，长会话才触发
  - **不启用 session-dedup / CCR**：它们用 `[dedup:ref sha=]` / `[CCR retrieve]` marker，依赖调用方广告 `omniroute_ccr_retrieve` 工具才能"取回原文"。Claude Code 不会广告，marker 被模型当乱码→丢内容
  - **不启用 contextEditing**：仅 `claude` 或 `anthropic-compatible-cc-*` 前缀端点才注入，opencode provider 不是
- 配置 API：
  - `GET /api/settings/compression`（Bearer OpenClaw gateway key 即可，本地 loopback bypass）
  - `PUT /api/settings/compression` body = `compressionSettingsUpdateSchema`（strict zod）；详见 `docker exec omniroute cat /app/src/shared/validation/compressionConfigSchemas.ts`
  - `POST /api/compression/preview` 用 `messages[]` + `mode` 验证实际压缩率（绕开鉴权可能 401，PUT 更直接）
- 持久化：写入 SQLite key_value namespace `compression`，每键一条 row。配置改动后重启 OmniRoute 才加载（`docker restart omniroute`）。
- 备份：`~/.openclaw/omniroute-config-backups/compression-YYYYMMDD-HHMMSS.json`（GET 全量 → 写盘）
- 回滚：`curl -X PUT -H "Authorization: Bearer sk-58b8c832...9e226e5d" -H "Content-Type: application/json" -d @~/.openclaw/omniroute-config-backups/compression-*.json http://127.0.0.1:20128/api/settings/compression`
- preview 真实样本（CC 多轮 + pytest 输出 ~1.3KB）：1324→1037 tokens，**22% savings, 9ms**（techniques: rtk-filter+caveman-rules，44 个 code/URL/error 行被 preserveBlocks 保护）

## 反检测浏览器栈（2026-08-13 部署，arm64 Pi）

- **位置**：`~/stealth/`（browse.py 主 CLI 已软链 ~/.local/bin/stealth-browse；stealth_check.py 指纹验证；README.md 文档），venv `~/.venvs/stealth`（patchright 1.61.2 + camoufox）
- **内核**：patchright + 完整 Chromium 149（channel="chromium"，非 headless shell），npmmirror 下载；UA 手动覆盖真实 Chrome UA；注入 deviceMemory=8 + WebGL 伪装（AMD Radeon，headless 软渲染是已知 bot 信号）
- **验证**：bot.sannysoft.com 27 项检测全过（webdriver 属性彻底删除、permissions=prompt、plugins=5、CDP/$cdc_ 清除、Phantom/Selenium 全过）；VIDEO_CODECS WARN 属无头正常现象
- **教训**：① 不要用 Object.defineProperty 伪装 webdriver——属性存在即被标记，patchright 的"彻底删除"才是对的；② patchright 补丁只打在完整 Chromium 上，默认 headless shell 补丁不全
- **人味操作**：browse.py 内置 human_delay/human_scroll/human_move（ease-in-out 曲线）/human_type；profile 持久化到 ~/stealth/profiles/<name>/state.json
- **camoufox**（备用，Firefox 内核，指纹随机化）：已装 152.0.4-beta.28（gh-proxy.com 下载 653MB 后按 multiversion.py 规范手动放置 ~/.cache/camoufox/browsers/official/152.0.4-beta.28-3a105a2f/ + version.json + config.json 激活）；⚠️ 大陆 AMO 451 拦 UBO 下载，必须 `exclude_addons=[DefaultAddons.UBO]` 否则卡启动；sannysoft 实测 webdriver=False + 真实 Firefox UA（Chrome 检测项标红是 Firefox 无 window.chrome 属正常）
- 硬边界：交互式 Turnstile 不自动化破解，遇到停下等人工

## 批量邮箱体系（2026-08-13 部署）

- **capsolver**（Turnstile 打码，用户提供 key）：key ~/.capsolver/api_key，模块 ~/capsolver/solve.py（软链 capsolver-solve）；用法 `capsolver-solve <url> <sitekey>` 或 `--balance`；余额 $6
- **mail.tm 批量邮箱**（主方案，API 直建免验证码）：工具 ~/mailtm/mailtm.py（软链 mailtm，子命令 create/inbox/read/wait）；默认账号 kuroneko33617@emalupe.com，凭据 ~/.mailtm/；批量账号自动追加 ~/.mailtm/accounts.json
- **tinkmail**（备选，已注册 kuroneko@tinkmail.me）：注册 API 逆向结论 = POST https://tinkmail.me/api/sign-up，body {isBusiness, name, account, secureEmail, password, password2, agree, honeypotGender:"", honeypotNorobot:false, turnstileToken}；sitekey 0x4AAAAAACUV5m2O7QYOJFQV（GET /api/config/turnstile 可拿）；脚本 ~/stealth/tinkmail_signup_v5.py
- 注册表单蜜罐：性别单选 + "I am not a robot" 复选框（name= honeypot_*），真人看不见，自动化千万别填
- 安全邮箱约定：批量注册一律用 agently kuroneko0804@agent.qq.com
- 教训：patchright 下 challenges.cloudflare.com/api.js 下载但不执行（window.turnstile 不定义），Turnstile 组件不渲染；浏览器注入方案不可行，直接逆向注册 API 才是正解

## Related

- [Agent workspace](/concepts/agent-workspace)

## Claude Code 回归主力（2026-08-24 反转，opencode 已卸）
- **背景**：08-23 曾卸载 CC 换 opencode 主力；08-24 14:00 用户嫌 opencode run 一轮式/守护循环有洞/网页端看不到后台进度，弃 opencode 回归 **Claude Code v2.1.241**（Agent Team 原生多 Agent 更适长跑）；opencode CLI 已删、opencode-web inactive（若复用见下方历史配置）
- **provider**：cc-switch `omniroute-free-nvidia`（全角色 opus/sonnet/haiku/fable/subagent = free-nvidia；free-all 组合实测超时/不稳弃用）；cc-switch 仍管 omniroute/minimax/omniroute-opencode 配置，llm-provider-sync 每日 00:00 仍跑
- **⚠️ env 进程级注入（CC 不读 settings.json 的 env）**：CloudCLI 走 ~/.cloudcli/.env + ~/.local/bin/cloudcli_start.sh（eval 读 settings.json env 再 exec）；终端走 ~/.bashrc（⚠️ 第 9 行非交互 return，`bash -lc` 不生效，测试用 pty）
- **长跑 = Stop Hook + 单会话**：~/.claude/settings.json hooks.Stop，exit 2 同会话续跑直到目标标记文件（~/TinyMind/docs/.tinymind_done）出现才 exit 0；`claude --bg` 第三方 provider 不持久化弃用；权限用 `--permission-mode acceptEdits`
- **CloudCLI**：http://localhost:8263（默认 3001 被 ~/apps/ruflo-bridge 占用）；claude_longrun.sh（env + --autocompact 200k）就位
- **TinyMind 晨报**：~/.openclaw/scripts/tinymind_daily_report.sh v3，07:00 cron 投递 QQ，读 ~/.claude/projects/-home-zyt-TinyMind/*.jsonl 最新会话；内容三件事（在干什么/下一步/离目标多远）
- 历史 opencode 配置（v1.18.18、5 插件、22 skills、无密码 web :4096）保留在 profile.md/lessons.md/opencode-ops 提案，踩坑：完整 ref、插件 -g、SSE 流、Basic auth

## OmniRoute combo 上下文误标 128K 修复（2026-08-25）
- **坑**：Claude Code 守护循环反复报 `Prompt is too long/compaction failed` + OmniRoute 日志 `Combo context limit: 128000 (source=combo-min)`。根因是 OmniRoute 模型目录给 `nvidia/nvidia/nemotron-3-ultra-550b-a55b` 误标 `context_length:128000`，`computeComboContextLength` 取 combo-min 用了它，在请求到上游**之前**就被自己拦 400。上游真实是 1M（实测 189K token 请求 HTTP 200）。
- **修复**：`PUT /api/combos/b4b33503-465a-4cc9-bff4-d8270f6d8807`（free-nvidia）显式设 `context_length:1000000`（显式值优先级最高，绕过 per-model 目录误标）→ 确认 `computed_context_length:1000000` → `docker restart omniroute` → Claude Code 窗口 `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 118K→950K（guard_loop.sh + tinymind-guard-loop.service）。
- **验证法（关键，别信目录值）**：构造超过疑似上限的大请求实测上游。本次 ~756K 字符/189K token POST `/v1/chat/completions` → HTTP 200/27s/complete 实锤上游 1M。
- **配套**：改 combo 前必 GET /api/combos 全量核对 + 备份到 `~/.openclaw/omniroute-config-backups/`（本次 free-nvidia-20260825-181458.json）。

## OmniRoute 重负载准入限流修复（2026-08-23）
- **问题**：cron 晨报（~9 万 token、756KB 请求体）反复 503/回退 deepseek；配置层全对仍不行
- **根因**：503 `chat_admission_busy` = OmniRoute 网关入口 admission control 拦截（非模型问题，未发到上游）。默认阈值：LARGE_BODY_BYTES=256KB / HEAVY_ESTIMATED_TOKENS=3.2万 / MAX_HEAVY_IN_FLIGHT=1 / HEAVY_MESSAGE_COUNT=200 / HEAVY_TOOL_COUNT=64 / HARD_MAX_MESSAGES=800
- **修复**：新建 /app/data/.env 放宽（4MB/128K/5/600/128/1200）+ `docker restart omniroute`（bootstrapEnv 优先级 process.env > DATA_DIR/.env > server.env；data volume 不丢、容器定义不动）
- **验证**：756KB→200（2.9s），晨报 cron 实跑 model=free-nvidia 不回退
- **配套**：~/.openclaw/scripts/omniroute-models-warmup.sh + user systemd omniroute-models-warmup.timer（每 4min 预热 /v1/models；cron preflight GET /v1/models 硬超时 2500ms，冷启动 2.5~5.7s 会超）
- 细节：memory/omniroute-admission-fix.md + omniroute-ops skill v3
