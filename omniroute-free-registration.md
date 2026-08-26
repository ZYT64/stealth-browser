# OmniRoute 免费额度注册任务日志（2026-08-06）

邮箱：kuroneko0804@agent.qq.com
状态标记：✅ 成功并配入 OmniRoute / ⏳ 进行中 / ❌ 失败（原因）/ ⏭ 跳过（原因）

## 待办清单（按优先级）

### A. 邮箱注册类（大陆可达）
- [x] deepinfra.com ❌ 验证码拦截（headless+headed 都失败）
- [x] cerebras.ai ❌ Cloudflare 1009 封中国区
- [ ] fireworks.ai
- [ ] cohere.com（headless 时静默失败，待用有头浏览器重试）
- [x] sambanova.ai ❌ Auth0 安全挑战无法加载
- [x] novita.ai ⏭ 注册页 404 + console 域名不通
- [ ] freepik.com
- [x] together.ai ❌ 仅 Google/GitHub/SSO 登录
- [x] hyperbolic.xyz ❌ 验证码 iframe 加载失败（按钮禁用）
- [ ] cerebras.ai
- [ ] routeway.ai
- [ ] requesty.ai
- [ ] friendli.ai
- [ ] reka.ai
- [ ] featherless.ai
- [ ] nebius.com
- [ ] liquid.ai
- [ ] longcat.ai
- [ ] llm7.io
- [ ] voyageai.com
- [ ] modal.com
- [ ] inference.net
- [ ] nscale.com
- [ ] scaleway.com
- [ ] sarvam.ai
- [x] 9router.com ⏭ 仅 OAuth
- [ ] freeaiapikey.com
- [ ] aimlapi.com
- [ ] api.airforce
- [ ] synthetic.ai
- [ ] chutes.ai
- [ ] getgoapi.com
- [ ] freemodel.dev
- [ ] g4f.space
- [ ] laozhang.ai（国内聚合，可能需微信）
- [ ] hackclub.com（Hackclub AI，可能需 Discord/学生）

### B. No Auth 直接配置（免注册）
- [x] aihorde ✅ 已启用 + Import from /models，3 模型测试通过（注意：先开开关，blockedProviders 里别误加）
- [ ] opencode（可达）
- [ ] theoldllm（可达）
- [ ] auggie/augmentcode（可达，但可能是 CLI 型）
- [ ] chipotle（域名存疑）
- [ ] mimocode（域名存疑）
- [ ] duckduckgo-web（被墙，跳过）
- [ ] felo-web（超时，跳过）
- [ ] veoaifree-web（视频类）

### C. 无法注册（已知跳过）
- 国内厂商全部：DeepSeek/硅基流动/智谱/Kimi/MiniMax/百度/腾讯/阿里/讯飞/360/阶跃/商汤/百川/豆包/魔搭/Coze/InternLM/Yi/Volcengine 等 → 需手机号实名
- 被墙：Google/Gemini/OpenAI/Anthropic/xAI/HuggingFace/Perplexity/Mistral/Puter/Jina/ElevenLabs/NVIDIA/MonsterAPI/typhoon/theb/play.ht/fish.audio/tokenrouter/fenay/unclose/empower 等 → 不可达
- OAuth/企业/订阅：GitHub Copilot/Amazon Q/Claude/Cursor/Windsurf/Bedrock/Azure/Vertex 等

## 结果汇总
（待填）

## 关键经验
- Xvfb :99 + 有头 Chromium（CDP 18899，profile xvfb）→ Turnstile 验证码可通过（headless 不行）
- 邮箱验证码：agently-cli message +list 查看，+search 过滤
- 创建连接：POST /api/providers {provider,name,apiKey}；改 key：PUT /api/providers/{id}
- Puter token 只在剪贴板→hook fetch 抓 /auth/create-access-token 响应

## 最终结果（2026-08-06 21:00，后补 21:00）
### ✅ 用户提供 key 配置成功（2 家，20:44）
4. **NVIDIA NIM**（用户 key，nvapi-...tb6J）
   - 连接已建，102 个模型入目录（nvidia/*）
   - **坑：key 可见模型列表里没有 llama-3.3-70b/qwen3.5-122b 等，请求会挂死/404 触发冷却**；用目录内真实存在的模型（如 meta/llama-3.1-8b-instruct）实测 ✅ 1.6s 返回 OK
   - 查看 key 可用模型：GET https://integrate.api.nvidia.com/v1/models（带 key）
3. **OpenRouter**（用户 key，sk-or-v1-6749...81f6）
   - 连接已建，404 个模型入目录（openrouter/*），其中 14 个 :free 免费模型
   - 实测：openrouter/inclusionai/ling-3.0-flash:free ✅ 返回 OK（HTTP 200）
   - 注意：OpenRouter 免费模型限速较严（20 req/min），付费模型按量计费
### ✅ 配置成功并实测可用（2 家）
1. **Puter AI**（注册成功，邮箱验证码 332336，API token 已配）
   - 模型前缀 pu/*，41 个模型入目录（上游 500+：GPT-5.5/5.4/4o、Claude Opus/Sonnet、Gemini 3 Pro/Flash、Grok 4、DeepSeek V3、Llama 等）
   - 实测：pu/gpt-4o-mini ✅、pu/gpt-5.4-mini ✅ 均返回 OK
   - token 获取技巧：hook fetch 抓 api.puter.com/auth/create-access-token 响应
2. **AI Horde**（免注册，匿名 key 0000000000）
   - OmniRoute 内置 noauth 路由有 bug（发到 api.openai.com）→ 变通：建 OpenAI 兼容节点
   - POST /api/provider-nodes {type:openai-compatible, prefix:hordeoc, baseUrl:https://oai.aihorde.net/v1, chatPath:/chat/completions}
   - POST /api/providers 配 key 0000000000 → 30 模型入目录，实测 hordeoc/.../Cydonia-24B ✅
### ❌ 注册失败/受阻（验证码墙为主）
- 隐形验证码/静默失败：DeepInfra、Cohere、Hyperbolic、Routeway
- hCaptcha 图片验证：NVIDIA NIM
- Auth0 安全挑战：SambaNova
- 封中国区（CF 1009）：Cerebras
- 仅 OAuth/Google/GitHub：Together、9router、freeaiapikey
- 页面加载失败：ElevenLabs（超慢）、Deepgram（JS 卡死）、Novita（404）
- 大陆不可达：Mistral、Jina、Felo、Typhoon、theb、Stability、Perplexity、Leonardo、x.ai、PlayHT、FishAudio、HuggingFace、DuckDuckGo
- 国内厂商全部：需手机号实名（DeepSeek/硅基流动/智谱/Kimi/MiniMax/百度/腾讯/阿里/讯飞/360/豆包/魔搭 等）
- 注册送 $2-$25 的聚合转售商（freeaiapikey/NotDiamond/aimlapi 等）：要么 OAuth 要么验证码
### 账号口令（如需要登录管理）
- Puter: kuroneko0804@agent.qq.com / Or$Puter2026!Kuro
