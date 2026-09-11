# 深知可信搜索（法律、政策、标准）（skills.sh Public 版）

这是深知可信搜索（法律、政策、标准）的 skills.sh Public 分发版本。功能逻辑与 full 版 1.1.0 对齐，不再调用统一咨询接口，默认只调用可信搜索接口；深度搜索仅在用户明确要求或确认升级后调用。本版本不内置 API Key；优先从环境变量 `DKNOWC_API_KEY` 读取，宿主进程读不到 shell 环境变量时自动从 `~/.zshrc` 兜底解析（避免 WorkBuddy 等宿主误报缺 Key）。未配置时，Agent 可先通过 MaaS 手机号验证码流程获取 Key，让当前任务临时继续执行；持久化环境变量是独立步骤，必须在用户明确同意后再处理。

## 能力范围

- 可信搜索：查找原文、依据、权威材料或来源时，调用 `scripts/trusted_search.py` 返回重点材料和知识专库链接。
- 深度搜索：仅在用户明确要求或确认升级后，调用 `scripts/deep_query.py`（deep-query/v3，非流式）做多轮检索和分析。
- 最终交付：直接回复答案、溯源核验报告 HTML、无来源角标的干净 Markdown。
- 默认核验报告：最终解决问题时，用 `scripts/render_trace_html.py` 生成《标题_溯源核验报告_时间戳.html》（首屏核验报告单五项指标：依据溯源/引用对应/材料新旧/材料构成/交付前检查，全部真实计算；生成前硬校验答案必须有 [n] 角标），并同步生成同名 `.clean.md`；`--self-check-file` 传入答案自检结果。
- 宿主环境交付：交付前运行 `scripts/deliver_outputs.py`，自动探测宿主工作区（WorkBuddy 等）复制产出物并返回用户可见路径。
- 政策可视化：用户明确要求图表时，用 `scripts/render_policy_visualization.py` 基于结构化 JSON 生成自包含 HTML 报告（可选 `--svg` 静态快照），以"清楚展示搜索数据"为原则——首屏数据表 + 每指标简单柱状图，覆盖城市对比/补贴金额/办理流程/时间线四类场景，来源收敛到行级与页脚。

## 首次启动初始化

只要调用本 Skill，Agent 必须先运行：

```bash
python3 scripts/initialize.py
```

只有返回 `ready=true`、`api_key_configured=true`、`api_key_source` 为 `environment` 或 `zshrc`，且未返回 `search_ready=false` 后，才继续处理原任务。初始化未通过时，只允许引导用户完成 MaaS Key 获取或环境变量配置，不得先输出答案、草稿、大纲、材料清单或分析结论。

## MaaS 注册与环境变量配置

当前版本统一通过环境变量 `DKNOWC_API_KEY` 注入 Key，不再扫描或复用其他深知系列 Skill 的本地 `config.ini`，业务调用脚本也不再读取本地配置文件或传入 `szUserId`。如当前环境变量未配置：

- 可运行 `scripts/register_key.mjs` 发送验证码并注册/查回 Key（send/register 各分支输出 `user_message` 固定话术，Agent 必须原样转述）。
- 注册成功后，脚本自动把 Key 以标记块形式写入 `~/.zshrc`（幂等替换，权限 0600；`--no-zshrc` 跳过）；业务脚本与 `initialize.py` 直读该文件，无需重启宿主。
- 返回的 `apiKey` 同时供当前任务临时注入 `DKNOWC_API_KEY` 继续执行。
- MaaS 平台登录页：`https://platform.dknowc.cn/auth/#/login`

## 开通引导（1.2.1 起固定话术）

初始化检测到 Key 未配置时输出 `guide_message`（S1 三段式：价值 / 权益+开通方式 / 退路+样例钩子），Agent 优先原样转述；注册漏斗与报错场景的完整固定话术见 `reference/onboarding_scripts.md`（S1-S6 场景话术、注册与搜索链路报错对照表、FAQ、通用禁则）。核心纪律：引导前禁示（确认前不得输出"已核实/已查到"类内容）、权益前置（300 次免费额度 + 实名认证赠金在引导时告知）、退路唯一（"依据待核验"标注，禁止承诺联网检索替代）、手机号全程脱敏。用户犹豫或询问效果时，用 `reference/sample_search_result.md` 与 `reference/sample_trace_report.html` 展示检索结果和溯源报告效果（两文件均为示例数据，仅供展示，不得作为交付物）。

## 接口地址

- 可信搜索接口：`https://open.dknowc.cn/dependable/search`
- 深度搜索接口：`https://open.dknowc.cn/api/services/deep-query/v3`（非流式，请求体字段 `query`，`areas` 支持多地域）
- MaaS 平台登录页：`https://platform.dknowc.cn/auth/#/login`

## 工作区与产物约定

本 Skill 的所有中间产物与交付物统一落在 Skill 目录下的 `official-docs/` 工作区，不再向 `/tmp` 或顶层 `outputs/` 写文件：

- `official-docs/search-results/`：查询/搜索/深度搜索结果 JSON 与答案文件。
- `official-docs/output/`：可点击溯源 HTML、干净 Markdown、可交互政策可视化 HTML 报告（及可选 SVG 快照）等最终交付物。

查询脚本配合 `--json-only --output <文件名>` 原生落盘到 `search-results/`；渲染脚本自动从 `search-results/` 读取、向 `output/` 写入。

## 常用测试

```bash
python3 -m py_compile scripts/api_key.py scripts/initialize.py scripts/trusted_search.py scripts/deep_query.py scripts/render_trace_html.py scripts/render_policy_visualization.py scripts/deliver_outputs.py scripts/check_release.py
node --check scripts/register_key.mjs
python3 scripts/check_release.py
```

请求参数检查：

```bash
python3 scripts/trusted_search.py "公积金租房提取政策原文" --show-payload --dry-run
python3 scripts/deep_query.py "重庆智能化改造补贴和税惠综合判断" --area 重庆 --show-payload --dry-run
```

公开包不得包含 `_meta.json`、`CHANGE_log.md`、`config.ini`、`config.ini.example`、`register.mjs`、真实 API Key、本地生成的 HTML/SVG 输出或缓存文件；`official-docs/` 工作区内只允许保留 `.gitkeep` 占位。
