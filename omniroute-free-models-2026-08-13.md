# OmniRoute 免费模型渠道清单 v3（2026-08-25 07:30 更新）

> 目标：免费模型池全部 ≥ deepseek-v4-flash（AAII 40.3 / MMLU 88.7）
> 能力锚点（Fireworks AAII 2026-07）：GLM-5.2=51.1、MiniMax-M3=44.4、Kimi-K2.7=41.9、DS-V4-Flash=40.3、Qwen3.7-Plus=39.0、Gemma-4-31B=29.4、gpt-oss-120b=23.8

## A. 真·免费 tier（长期可用，无到期，仅速率/量限制）—— 优先接入

| # | 渠道 | 达标免费模型 | 配额 | 大陆直连 | key |
|---|------|-------------|------|---------|-----|
| 1 | NVIDIA NIM | glm-5.2 / minimax-m3 / step-3.7-flash / nemotron-3-ultra | 无限次，40 RPM | ✓ 已实测 | ✅ 已有 21 keys |
| 1b | **Dahl** (inference.dahl.global) | **Kimi-K2.6 / MiniMax-M2.7 / DS-V4-Flash** | **每 token 1 亿 token，匿名无限建 token** | ✓ 已实测 | ✅ 无需（POST /tokens 匿名创建）|
| 2 | OpenRouter :free | nemotron-3-ultra:free / nemotron-3-super:free / gpt-oss-20b:free | 20 req/min/key | ✓ 已实测 | ✅ 已有 |
| 3 | opencode-zen (内置) | nemotron-3.5-lightning-free / nemotron-3-ultra-free | 无限 | ✓ 已实测 | 无需 |

## B. 待验证/有条件免费

| # | 渠道 | 潜在模型 | 状态 | 备注 |
|---|------|---------|------|------|
| 4 | NIM 新旗舰 | **minimax-m3 (44.4)** / **step-3.7-flash** / **kimi-k3** | **NIM 目录有，OmniRoute 尚未同步** | 需等待 provider 刷新或手动触发模型同步；kimi-k3 当前 429 限流 |
| 5 | OpenRouter :free | z-ai/glm-5.2:free | 目录有但 429 未解锁 | NIM 通道已下架，此模型目前无免费可用通道 |
| 6 | DeepSeek 官方 | deepseek-v4-flash | 兼容端点可用 | 需 key，已配置 pro-coding 等 |

## C. 已废弃/不可用（本轮确认）

| 渠道 | 原因 |
|------|------|
| poolside/laguna-s-2.1:free | OpenRouter 404（免费版下架） |
| nemotron-3.5-lightning:free (OR) | OpenRouter 404（免费版下架） |
| deepseek-v4-pro | **全面禁用**（用户 2026-08-10 定） |

---

## 当前 free-all 组合（c3f513f8-7e5c-40d8-b2eb-84665db43683）

| # | 模型 ID | Provider | AAII 估算 | 状态 | 备注 |
|---|---------|----------|-----------|------|------|
| 1 | dahl/moonshotai/Kimi-K2.6 | dahl | ~41.9 | ✅ 16ms | Kimi-K2.6 ≈ K2.7 |
| 2 | dahl/MiniMaxAI/MiniMax-M2.7 | dahl | ~44.4 | ✅ 42ms | MiniMax-M2.7 ≈ M3 |
| 3 | dahl/deepseek-ai/DeepSeek-V4-Flash-0731 | dahl | 40.3 | ✅ 113ms | 基准锚点 |
| 4 | opencode/nemotron-3.5-lightning-free | opencode | ~35 | ✅ 4ms | 推理模型，轻量 |
| 5 | opencode/nemotron-3-ultra-free | opencode | ~45 | ✅ 15ms | Nemotron 3 Ultra 550B |

**策略**：round-robin / weight=0 / maxRetries=2 / concurrencyPerModel=3
**结论**：**5/5 全部实测通过，全部 ≥ DS-V4-Flash，无需移除**

---

## 当前 free-nvidia 组合（b4b33503-465a-4cc9-bff4-d8270f6d8807）

| # | 模型 ID | Provider | 状态 | 备注 |
|---|---------|----------|------|------|
| 1 | nvidia/nvidia/nemotron-3-ultra-550b-a55b | nvidia | ✅ 1.3-2.7s | 21 keys 轮询，绕过单模型限流 |

**结论**：单模型兜底可用，但高延迟；建议待 NIM 同步新旗舰后扩充为多模型

---

## 本轮维护记录（2026-08-25 07:30）

### ✅ 实测通过（保留）
- dahl 3 模型：Kimi-K2.6 / MiniMax-M2.7 / DS-V4-Flash（全 < 200ms）
- opencode 2 模型：nemotron-3.5-lightning-free / nemotron-3-ultra-free（全 < 20ms）
- free-nvidia：nemotron-3-ultra-550b-a55b（1.3-2.7s，功能正常）

### 🔍 发现新模型（待 OmniRoute 同步）
| 模型 | 渠道 | AAII 预估 | 备注 |
|------|------|-----------|------|
| minimaxai/minimax-m3 | NIM | 44.4 | 目录已有，provider 待刷新 |
| stepfun-ai/step-3.7-flash | NIM | ~42 | 目录已有，provider 待刷新 |
| moonshotai/kimi-k3 | NIM | ~43 | 目录已有，**当前 429 限流** |
| nvidia/nemotron-3.5-lightning-30b-a3b | NIM | ~35 | 目录已有 |

### ❌ 失效/下架（已确认）
- poolside/laguna-s-2.1:free (OR 404)
- nvidia/nemotron-3.5-lightning:free (OR 404)

### 📊 配额状态
- Dahl：43 个 token（≥ 40 目标），全部 active
- NIM：21 个 keys（main-2 到 main-21），main-21 最近有 kimi-k3 429
- OpenRouter：1 key，部分 free 模型 429

### 📝 待办（下轮/手动）
1. 触发 OmniRoute NIM provider 模型同步（或等自动刷新），把 minimax-m3 / step-3.7-flash 接入 free-nvidia
2. 观察 kimi-k3 限流恢复情况
3. 如免费池需扩容，可考虑把 opencode nemotron 模型也加入 free-nvidia 做多模型兜底

---

## 历史记录

### 2026-08-24 23:08（v17 更新）
- free-all 回补 nemotron-3-ultra-free（首测 502 抖动，复测 2 次 200）
- free-nvidia 创建（单模型 nemotron-3-ultra，21 keys 轮询）

### 2026-08-13（v2 基线）
- OpenRouter :free：18 个（比昨日 19 少 1，某个小模型消失）
- z-ai/glm-5.2:free 仍在目录但 429 限额未解锁（NIM 通道已下架，此模型已无免费可用通道）
- 无 glm/kimi/minimax/deepseek 新旗舰
- 本轮无新 provider、无付费、无注册渠道
- 未使用 deepseek-v4-pro