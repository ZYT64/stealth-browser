# CLAUDE.md — Claude Code 工作规范（本工作区）

> 本机已有本地 AI 网关 OmniRoute（http://127.0.0.1:20128/v1），已通过 cc-switch 接入（provider: omniroute）。
> 当前生效模型配置：默认 pro-coding，opus=pro-reasoning，sonnet=pro-coding，haiku=free-fast。

## 模型分配策略（必须遵守）

### 简单任务 → 免费模型（haiku 档，自动用 free-fast）
- 代码格式化、翻译、注释补充、简单问答、单文件小改动、文档润色
- 不得在这些任务上浪费付费模型

### 常规编码任务 → pro-coding（sonnet 档/默认）
- 写代码、修 bug、重构、补测试、Code Review

### 高难度任务 → pro-reasoning（opus 档）
- 架构设计、疑难 bug 排查、跨模块推理、性能优化、长上下文分析

### 红线
- ❌ **严禁把复杂任务交给免费模型**（free-* 只服务简单任务，质量不可靠）
- 免费模型（haiku/free-fast）限速明显，长任务不要依赖它

## 并行子 Agent
- 重任务优先拆分为多个独立子 Agent 并行执行（Claude Code 子代理），各自按复杂度选模型
- 简单子任务用 haiku（免费），核心子任务用 sonnet/opus

## 环境说明
- 网关：http://127.0.0.1:20128/v1（OpenAI + Anthropic 格式都支持）
- Combo：free-fast / free-chat / free-coding（免费）；pro-coding / pro-reasoning（DeepSeek 自家账户付费，OpenRouter 仅 :free 免费源、不依赖其余额）
- 模型名直接用 Combo 名（如 `free-fast`），也可用 `auto/coding`、`auto/fast`、`auto/cheap` 让 OmniRoute 自动路由
- 若每日 00:00 同步后 provider 被切回 deepseek：`cc-switch use omniroute` 切回
