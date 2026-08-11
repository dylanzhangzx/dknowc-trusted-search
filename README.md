# 深知可信搜索（法律、政策、标准）（skills.sh Public 版）

这是深知可信搜索（法律、政策、标准）的 skills.sh Public 分发版本。功能逻辑与 full 版 1.1.0 对齐，不再调用统一咨询接口，默认只调用可信搜索接口；深度搜索仅在用户明确要求或确认升级后调用。本版本不内置 API Key；首次调用时必须先确认环境变量 `DKNOWC_API_KEY` 已配置。未配置时，Agent 可先通过 MaaS 手机号验证码流程获取 Key，让当前任务临时继续执行；持久化环境变量是独立步骤，必须在用户明确同意后再处理。

## 能力范围

- 可信搜索：查找原文、依据、权威材料或来源时，调用 `scripts/trusted_search.py` 返回重点材料和知识专库链接。
- 深度搜索：仅在用户明确要求或确认升级后，调用 `scripts/deep_query.py` 做多轮检索和分析。
- 最终交付：直接回复答案、可点击溯源 HTML、无来源角标的干净 Markdown。
- 默认溯源 HTML：最终解决问题时，用 `scripts/render_trace_html.py` 生成可点击溯源 HTML，并同步生成同名 `.clean.md`。
- 政策可视化：用户明确要求图表、热力图、雷达图或区域对比图时，用 `scripts/render_policy_visualization.py` 生成一张可直接展示的 SVG 图片，不生成可视化 HTML。

## 首次启动初始化

只要调用本 Skill，Agent 必须先运行：

```bash
python3 scripts/initialize.py
```

只有返回 `ready=true`、`api_key_configured=true`、`api_key_source=environment`，且未返回 `search_ready=false` 后，才继续处理原任务。初始化未通过时，只允许引导用户完成 MaaS Key 获取或环境变量配置，不得先输出答案、草稿、大纲、材料清单或分析结论。

## MaaS 注册与环境变量配置

当前版本统一通过环境变量 `DKNOWC_API_KEY` 注入 Key，不再扫描或复用其他深知系列 Skill 的本地 `config.ini`，业务调用脚本也不再读取本地配置文件或传入 `szUserId`。如当前环境变量未配置：

- 可运行 `scripts/register_key.mjs` 发送验证码并注册/查回 Key。
- `register_key.mjs` 只返回 Key，不持久化保存 Key。
- 当前任务拿到 Key 后可临时注入 `DKNOWC_API_KEY` 并继续执行。
- 任务完成后，Agent 询问用户是否需要持久化 `DKNOWC_API_KEY`；用户同意后再单独处理。
- MaaS 管理平台地址：`https://platform.dknowc.cn/`

## 接口地址

- 可信搜索接口：`https://open.dknowc.cn/dependable/search`
- 深度搜索接口：`https://open.dknowc.cn/api/services/deep-query/v2`
- MaaS 管理平台：`https://platform.dknowc.cn/`

## 常用测试

```bash
python3 -m py_compile scripts/initialize.py scripts/trusted_search.py scripts/deep_query.py scripts/render_trace_html.py scripts/render_policy_visualization.py scripts/check_release.py
node --check scripts/register_key.mjs
python3 scripts/check_release.py
```

请求参数检查：

```bash
python3 scripts/trusted_search.py "公积金租房提取政策原文" --show-payload --dry-run
python3 scripts/deep_query.py "重庆智能化改造补贴和税惠综合判断" --area 重庆 --show-payload --dry-run
```

公开包不得包含 `_meta.json`、`CHANGE_log.md`、`config.ini`、`config.ini.example`、`register.mjs`、真实 API Key、本地生成的 HTML/SVG 输出或缓存文件。
