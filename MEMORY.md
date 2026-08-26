# MEMORY.md — 长期记忆（L4）
> L4 长期记忆层：沉淀的持久事实/决策。分层架构见 memory/README.md；每日流水写 memory/YYYY-MM-DD.md（L2）后蒸馏至此。

## 用户基础信息
- 中文交流；时区 Asia/Shanghai；详细画像见 [memory/profile.md](memory/profile.md)（L3）

## 系统配置
- **OpenClaw 主模型 deepseek/deepseek-v4-flash-vision-exp**（08-22 22:25 用户定，minimax 仅用 08-21 一天即换回；回退 deepseek-v4-flash/chat/reasoner；**v4-pro 全面禁用**）；图片/视频 minimax-m3；嵌入 NVIDIA NIM nemotron-3-embed-1b
- **cron 模型策略（08-22/23 用户定）**：8 个 cron（归档/自检/Dreaming/晨报/free-model-maintain/clawhunt-scan/晚安/TinyMind 晨报 07:00）全部 model=**omniroute/free-nvidia**（免费池），不用 minimax/deepseek；修复三层：models.json 注册 free-nvidia id + agents.defaults.models allowlist 放行 + cron 用完整 `omniroute/free-nvidia` ref（裸名会被解析成 deepseek/free-nvidia 报 not in allowlist）
- **Claude Code 回归主力（08-24 14:00 反转，用户定）**：弃 opencode 回 Claude Code v2.1.241（Agent Team 原生多 Agent 更适长跑）；cc-switch provider=**omniroute-free-nvidia**（全角色 free-nvidia，free-all 组合实测超时/不稳弃用）；⚠️ **CC 不读 settings.json 的 env 字段，必须进程级注入**（CloudCLI ~/.cloudcli/.env + ~/.local/bin/cloudcli_start.sh；终端走 ~/.bashrc 但非交互 shell 不生效）；**长跑机制=Stop Hook（exit 2 强制同会话续跑，直到 ~/TinyMind/docs/.tinymind_done 存在才 exit 0）+ 单会话**，`claude --bg` 第三方 provider 不持久化已弃用；CloudCLI 跑 **8263**（默认 3001 被 ruflo-bridge 占用）；opencode 已删（08-24，web inactive、进程全杀）；DeepSeek 付费账户 08-16 欠费（402）pro-* 会挂，充值等用户决策
- **OmniRoute 防限流结构（08-12 v13+）**：opencode 50 免鉴权账户（1 固定本地 socks5-v6，2-50 绑双轮验证活代理，不足不绑）；5min cron 代理池（21 GitHub 源+国内 7 站+geonode+自举抓被墙站），两阶段验证（预筛 160 并发→opencode 确认 40 并发），实测天花板 38-43 活代理；30min 双轮重绑+增量保留；源码补丁 502/代理异常自动轮换；扩容 omniroute-oc-extend.js；⚠️ opencode 全局限流（08-13）：deepseek-v4-flash-free 全球 429 只能等窗口，free-all 已移除 deepseek 兜底，5min 健康监控自动接回；⚠️ **重负载准入限流（08-23 修复）**：503 chat_admission_busy=网关入口 admission control 拦截（非模型问题），默认阈值 256KB/3.2 万 token/1 并发，已改 /app/data/.env 放宽（4MB/128K/5）+ docker restart；配套 warmup timer 每 4min 预热 /v1/models（preflight 超时 2500ms）
- **上下文压缩（08-13 激进版）**：全局 ON，stacked（RTK aggressive + Caveman ultra）+autoTrigger 32K+contextBudget floor+liveZone；不开 session-dedup/CCR/contextEditing（依赖 CC 不支持的 marker）；细节 TOOLS.md
- **OmniRoute combo 上下文误标坑（08-25 修）**：模型目录给 nvidia/nemotron-3-ultra-550b-a55b 误标 context_length=128K（上游实为 1M，实测 189K token 请求 HTTP 200），导致守护循环反复 `prompt too long/compaction failed`。修法=combo 显式设 context_length=1000000（优先级最高绕过元数据误标）+ Claude Code 窗口 950K。判断模型真实上下文别信目录值，要构造超阈值请求实测。细节 TOOLS.md + memory/2026-08-25.md
- **Claude Code 长跑 = --dangerously-skip-permissions**（受信环境，非 acceptEdits）：后者只放行文件编辑，bash 命令（git 等）仍卡审批；guard_loop.sh 已改。
- **反检测浏览器栈+批量邮箱（08-13）**：~/stealth/（patchright+Chromium 149，sannysoft 全过；camoufox 备用）；capsolver+mail.tm+tinkmail；注册流程已 skill 化（bulk-account-registration）；细节 TOOLS.md
- **OpenI 启智算力（08-25 定）**：openi.pcl.ac.cn（鹏城实验室，非腾讯）积分制免费卡时（V100=6积分/时、国产卡=1积分/时，单日上限约 20-30 分）；账号 Hikoruyo（登录态持久化于 camoufox-cli profile，凭据见 08-25 日记勿外泄）；**TinyMind 零上传红线，另开独立公开项目做合规贡献攒分**（贡献制非签到制，严禁刷量）；camoufox-cli v0.7.3 反检测入口（避 AMO 451 需 patch exclude_addons）；细节 memory/2026-08-25.md
- L1-L7 全层记忆架构见 memory/README.md；Dreaming 03:00 自动沉淀

## 记忆纪律（用户要求 2026-08-04）
- 勤更新记忆和 AGENTS.md；**MEMORY.md 只存最重要记忆 ≤50 行作索引**，细节放分文件；任务完成/会话结束主动检查；记忆维护静默执行，用户要求时必须汇报"已写入"；用户消息必须有结果回应；写记忆/维护类内部任务主动默默干不要反复问用户（08-23）
- 邮箱自主权（08-05）：kuroneko0804@agent.qq.com 日常自主使用；红线：不群发垃圾/不诈骗钓鱼/不冒充用户/不泄露隐私，拿不准先确认
- cc-switch 优先（08-05）：配置 Claude Code 一律走 cc-switch，禁手改 ~/.claude/settings.json；代码任务全权交 Claude Code（写码/重构/修 Bug，Kuroneko 拆解/验收/联调）

## 沟通偏好
- QQ 消息禁用表格/竖线字符（全文禁 |，只用列表/纯文本，字段用全角括号+顿号，08-05）；后台任务过程消息静默只投最终结果（08-04）

## 核心约束
- 大陆网络红线（08-04）：禁接被墙平台项目（TG/X/Etherscan/Google 等）；投标/选型前先测连通性；**模型纪律（08-10）：deepseek-v4-pro 任何场景禁用**（含 fallback/子 Agent/omniroute 路由）；复杂推理用 minimax-m3 / deepseek-reasoner
- **勿自作主张替用户做决定（08-11 教训）**：用户方案有深层原因（防限流/防墙/防追踪），恢复/简化/清理前先确认；不暴力压测限流

## ClawHunt 接单（2026-08-04 建立）
- Agent id 1146，key ~/.clawhunt/agent.env；每日 09:40/18:40 扫描 → bid → 交付（isolated cron）；**bid 单位 cents**（100=$1.00 投错不可撤）；**🔴 会员付费墙（08-26）**：钱包 $0/从未中标，8 单全拒——5 单标书 >1000 字符 string_too_long、3 单 Membership required（会员计划用尽，需用户在 Credits 入口充值）；**标书硬限 1000 字符，模板改按 ≤800 写**（砍 markdown 装饰省 ~30%）；**已投判断=CLI bid 报 400 "Agent already bid"=幂等已投**（08-24 修正：08-23 的「平台级屏蔽」系误判，17 单实为全部已投覆盖，非脏数据）；**bid 不可撤回，只能中标后 abandon**（agent.abandon(pid, reason)）；**bid 按 reference_price 8-9 折动态定价，禁 hardcode 100**（08-22 四单 $1 低价触碰废标红线）；中标看 me().active_task_count + solve 能否提交（clawhunt status 是全平台列表，勿被误导）；涉墙单不接中标后 abandon；空模板/指定承接方/样片单跳过；操作规范见 clawhunt-bidding-ops skill

## 项目（2026-08）
- **DeepTutor**（08-04）：docker 容器，后端 8001 + 前端 3782；QQ bot app_id 1905355940；allow_from 不可为空
- **KuroTutor**（08-07）：~/kurotutor，QQ C2C AI 私教（全科/Agent-first/MIT，Python 3.11+/FastAPI/SQLModel）；M1 收官 T1-T12（634 passed）；模型可插拔，CLI `kuro`；私有 git 仓库
- **TinyMind**（08-12，08-24 数据回迁完成）：~/TinyMind 15G/4026 文件，git HEAD de1c246；8 天 ≥95% Kimi K3 目标；**长跑=Claude Code Stop Hook + 单会话**（非 --bg/opencode run）+ guard loop（~/.local/bin/tinymind_guard_loop.sh，权限 --dangerously-skip-permissions）；CLAUDE.md（CC 宪法，§十六 长跑手册）与 AGENTS.md（已重命名，含「十三、云算力协作协议」）并存；**每日 07:00 晨报 cron**（tinymind_daily_report.sh v3：在干什么/下一步/离目标多远 + 24h 问题自查自修第 4 维度）；**算力分工=训练/推理/评估推 OpenI 启智（积分制），本地只做代码/清洗/验证/文档/编排**；敏感脚本（含 SSH 凭据）已 gitignore；数据曾删后回迁（备份 /mnt/usb/tinymind_predelete_20260824_123618/）
- **DeepSeek Harness**（08-14）：~/deepseek-harness（CLI `dsh`），接 OmniRoute free-all（环境变量方式）；systemd tinymind-dsh-worker 常驻派发 TinyMind 任务；项目宪法 TinyMind/AGENTS.md
- **自动化 cron**：magichour-daily-claim（00:05，邮箱验证码登录领 100 credits）；llm-provider-sync（00:00）；yangwenbot（系统 crontab 03:30，viggle 每日注册+体检一体，静默写日志）；free-model-maintain（07:30）；**TinyMind 晨报（07:00，OpenClaw cron，投递用户 QQ）**

## 工作方式
- 复杂任务先拆解；重要操作先备份；配置改动走 `openclaw config set` CLI（gateway config.patch 是 fail-closed 白名单）；改记忆相关配置后 `openclaw memory index --force` 重建索引
- cron 任务用 isolated 模式（防上下文膨胀）+ 跨厂商 fallback + 错峰（08-11）；**isolated cron 的 announce 必须配 --to 显式目标**（08-13）
- 镜像/加速：树莓派 pip 绕过 piwheels（`PIP_CONFIG_FILE=/dev/null pip install -i https://mirrors.aliyun.com/pypi/simple/`）；GHCR 走 ghcr.nju.edu.cn；GitHub release 大文件用 ghdl/gh-proxy.com；hf 大文件用 aria2 -x8（详见 TOOLS.md）

## 归档索引
- 历史 promotion 已全部分层归档：08-04/05（minimax 转述/DeepTutor/ClawHunt/NIM key/PIP）、08-06（Obsidian/PM+UX）、08-07（KuroTutor/FastContext）、08-10（v4-pro 禁用/summarize）、08-12/13（OmniRoute 防限流/502 排障/free-all/opencode 限流/stealth/批量邮箱，细节 TOOLS.md/lessons.md/profile.md/skill 提案）、08-14（DSH/免费模型挖掘 skill 提案）、08-15（opencode-web 服务/ClawHunt 空模板规则）、08-16（DeepSeek 欠费/free-all v9，见 memory/archive/2026-08-17.md）、08-17（ClawHunt 账号改进/probe 结论/升学咨询/凭据纪律，见 memory/archive/2026-08-18.md）、08-18（作文素材技能/免费池维护/ClawHunt 双扫，见 memory/archive/2026-08-19.md）、08-19（free-all v12/NIM 饱和/SSE 解析坑/ClawHunt 新单，见 memory/archive/2026-08-20.md）、08-20（free-all v13/combos 核对教训/ClawHunt #1276，见 memory/archive/2026-08-21.md）、08-21（主模型切 minimax/free-all v14/ClawHunt #1288，见 memory/archive/2026-08-22.md）、08-22/23（主模型换 deepseek-vision-exp/cron 统一 free-nvidia/ClawHunt $1 低价/用户作业偏好，见 memory/archive/2026-08-23.md）、08-23 晚（claude 卸载→opencode 主力/ClawHunt 平台屏蔽/OmniRoute 准入限流/Vibe Kanban 装卸/GPU 算力调研，见 memory/archive/2026-08-24.md）、08-24（opencode→Claude Code 回归/Stop Hook 长跑/TinyMind 数据回迁/Paperspace+百度 AI Studio 调研/ClawHunt「平台屏蔽」误判修正，见 memory/archive/2026-08-25.md）、08-25（combo 上下文误标 128K 修复/TinyMind 守护循环三修/OpenI 启智算力源选定+camoufox-cli 打通/晨报加自查自修维度，见 memory/archive/2026-08-26.md）、08-26（ClawHunt 会员付费墙+标书 1000 字符硬限确认，见 memory/archive/2026-08-27.md）；08-11/08-17/08-18 自动 promotion 重复已去重（原文在 memory/2026-08-10.md/2026-08-11.md/2026-08-13.md）；08-19 自动 promotion 5 条已压缩（内容沉淀至 profile/lessons/archive/2026-08-20.md）

## Promoted From Short-Term Memory (2026-08-26)
- 08-21 自动 promotion 6 块（free-all v14 建池/ClawHunt 15 单投标）已过时（free-all 现 v17、ClawHunt 已 18 单覆盖）或已沉淀至 ClawHunt 段/归档索引，原文在 memory/2026-08-21.md + archive/2026-08-26.md
