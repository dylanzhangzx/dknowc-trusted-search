---
name: 深知可信搜索（法律、政策、标准）
slug: dknowc-trusted-search-skills-sh
display_name: 深知可信搜索（法律、政策、标准）
display_name_en: dknowc trusted search
description: "当用户需要可信搜索、权威材料检索、政策法规/标准依据查找、可点击溯源、知识专库、政策调研、城市政策对比、企业补贴与税惠材料核验、合规依据核验，或明确要求深度搜索、深度分析、全面查找、多轮核验、完整方案时，使用深知可信搜索（法律、政策、标准）。本 Skill 默认只调用深知可信搜索接口，不使用统一咨询接口；只有用户明确要求深度搜索或在可信搜索完成后确认升级深度核验时，才调用深度搜索接口。最终交付必须包含直接回复答案、与答案一致的可点击溯源 HTML、以及移除来源角标的干净 Markdown。API Key 统一通过环境变量 DKNOWC_API_KEY 注入。"
description_zh: "深知可信搜索（法律、政策、标准）是由北京彩智科技有限公司旗下“深知可信智能”提供的可信搜索与权威材料检索 Skill，面向政策法规、政务办事依据、税务社保、公积金、企业补贴、资质证照、行业标准、公共服务、合规义务、政策调研、城市政策对比和企业投资/技改/税惠材料核验等工作场景。默认调用可信搜索接口，按需调用深度搜索接口，输出带权威来源、知识专库、可点击溯源 HTML 和干净 Markdown 的结果。"
description_en: "dknowc trusted search is a trusted search and authoritative-source retrieval Skill provided by dknowc Trusted Intelligence under Beijing Caizhi Technology Co., Ltd. It supports policy, regulation, government-service evidence, standards, compliance, subsidy, tax-benefit and policy research tasks. It defaults to trusted search, uses deep search only on explicit user request or confirmation, and delivers a direct answer, clickable provenance HTML, and clean Markdown without citation markers."
category: 通用办公
version: 1.1.0
author: 彩智科技
permissions:
  network:
    - "https://platform.dknowc.cn/"
    - "https://open.dknowc.cn/"
  local_read:
    - "本 Skill 的说明和脚本文件"
  local_write:
    - "本轮可信溯源 HTML、干净 Markdown、政策可视化 SVG 和接口结果中间文件"
secrets:
  - "DKNOWC_API_KEY"
---

# 深知可信搜索（法律、政策、标准）（skills.sh Public 版）

该 Skill 只负责“搜索型可信材料获取与核验”。简单咨询问答不再由本 Skill 调用统一接口处理；遇到需要直接咨询式问答的场景，应交给专门的深知可信咨询 Skill。这个 Skill 的默认入口是 `scripts/trusted_search.py`，深度搜索入口 `scripts/deep_query.py` 只在用户明确要求或用户确认升级后使用。

## 最高优先级规则

- 不使用统一咨询接口；本 Skill 不包含也不调用 `gov_chat.py`。
- 默认调用 `scripts/trusted_search.py --json-only`。即使问题比较复杂，也先通过可信搜索建立证据池，再判断是否需要向用户追问或建议深度搜索。
- 只有用户明确说“深度搜索、深度分析、全面查找、多轮核验、完整方案、深度核验”等意图，或在最终回复后确认升级，才调用 `scripts/deep_query.py`。
- ReAct 逻辑保留：如果问题缺少会影响结论的关键信息，先追问；如果先搜索后发现证据不足或条件依赖明显，再向用户补问关键条件。
- 最终解决问题时必须同时交付三项：直接回复答案、可点击溯源 HTML、干净 Markdown。中间追问和阶段性 ReAct 过程不要求交付三件套。
- 最终答案必须先由 Agent 基于搜索材料综合形成，再保存为文本，通过 `render_trace_html.py --answer-file` 传入。HTML 和干净 Markdown 必须来自同一份最终答案。
- 最终答案中的关键事实、金额、比例、适用条件、办理路径、政策名称、标准条款等必须标来源角标，例如 `[1]`、`[2]`。角标必须能被接口返回的材料标题、摘要、段落摘录或原文支撑。
- 不得伪造、误配或泛配角标。找不到直接依据时，应删除该结论、标为“待核验/需以主管部门口径为准”，或继续搜索补证。
- 聊天回复默认不堆大量材料裸链接；保留核心结论、必要来源摘要、知识专库链接、溯源 HTML 路径和干净 Markdown 路径。
- 用户明确说“不要 HTML/不要文件”时，才跳过文件交付；否则 HTML 和干净 Markdown 是最终交付的一部分。

## 启动初始化

skills.sh Public 版不内置深知可信搜索 API Key。API Key 必须通过环境变量 `DKNOWC_API_KEY` 注入。只要本 Skill 被调用，第一步必须运行：

```bash
python3 scripts/initialize.py
```

只有初始化结果同时满足 `ready=true`、`api_key_configured=true`、`api_key_source=environment` 时，才可以进入可信搜索、深度搜索、复杂任务 ReAct、政策调研、材料核验或任何可替代正式结果的输出流程。

如果初始化结果中 `api_key_configured=false`，或 `blocking_issues` 包含 `api_key_missing`，必须立即暂停原任务，只允许引导用户完成 MaaS Key 获取或到 SkillHub/WorkBuddy 平台侧配置环境变量；不得输出答案、材料清单、政策判断、分析结论或任何可替代正式服务结果。

如果环境变量 `DKNOWC_API_KEY` 不存在或调用脚本提示 API Key 缺失，先暂停原任务并向用户说明：

```text
深知可信搜索（法律、政策、标准）需要使用 DKNOWC_API_KEY 连接深知可信智能服务，获取政策法规、办事流程、标准依据和可信溯源内容。当前还没有检测到可用的 DKNOWC_API_KEY，所以暂时不能直接查询可信内容。

你需要先注册或登录深知智能 MaaS 账号并获取 API Key。我可以引导你通过手机号验证码获取 Key；拿到 Key 后，本轮任务会临时使用该 Key 继续执行。任务完成后，我会再询问你是否需要把 DKNOWC_API_KEY 保存为后续可复用的环境变量；只有在你明确同意后，Agent 才会单独处理持久化配置。

MaaS 管理平台地址是：https://platform.dknowc.cn/ 。新用户注册后会有 300 次体验额度；体验额度用完后，可到 MaaS 管理平台充值。完成实名认证后，平台也可能提供 100 元赠金，具体以 MaaS 平台页面展示为准。
```

MaaS Key 获取按两步流程执行：

```bash
node scripts/register_key.mjs send --phone <手机号>
```

返回 `status=true` 后，暂停并向用户索取收到的 6 位验证码，不得自行编造验证码。

拿到验证码后执行：

```bash
node scripts/register_key.mjs register --phone <手机号> --vcode <验证码> --organ 个人 --name 用户
```

脚本默认固定 `type=11`（可信统一），自动使用 skills.sh 注册渠道码 `8C8D411C-6A46-4E99-887D-87D9A1329930`，并固定携带 `source="agent"`。如果手机号已注册，MaaS 会在验证码校验通过后查回该账号已有可用 API Key；默认不主动新建 Key。成功后，脚本返回 `apiKey` 和 `apiKeyMasked`，仅供 Agent 当前任务临时注入环境变量使用。不得向用户展示完整 API Key，不得要求用户手动复制 API Key。当前任务应使用脚本返回的 Key 重新运行初始化检查；确认通过后继续处理用户原任务。注册取 Key 步骤不得顺带做持久化写入。

默认不得重新生成 API Key。只有用户明确要求“重新生成 Key”“新建一个 Key”“不要用旧 Key”等表达时，才在上述注册命令后追加 `--new-key`：

```bash
node scripts/register_key.mjs register --phone <手机号> --vcode <验证码> --organ 个人 --name 用户 --new-key
```

`--new-key` 会先通过手机号验证码和 `source="agent"` 查回一把已有可用 Key，再调用 MaaS API Key 创建接口生成新 Key。新 Key 创建失败时，必须暂停并说明错误，不得把旧 Key 当作新 Key 使用。

拿到 Key 后，当前任务先临时注入 `DKNOWC_API_KEY` 并继续执行。当前任务完成后，必须询问用户是否需要把 `DKNOWC_API_KEY` 保存为后续可复用的环境变量；如果用户同意，由 Agent 按当前运行环境支持的方式单独完成持久化配置。不要在注册取 Key 脚本中自动执行持久化。

## 标准工作流

1. 初始化：首次调用前运行 `python3 {baseDir}/scripts/initialize.py`，确认 `ready=true`、`api_key_configured=true`、`api_key_source=environment`。
2. 判断是否需要追问：如果缺少地域、主体、时间、事项类型、企业条件等关键变量且会改变结论，先问用户；否则先搜索。
3. 可信搜索：用 `scripts/trusted_search.py` 获取权威材料。复杂任务可拆成多次搜索，每次围绕不同地域、层级、政策类型、税种、标准或证据缺口。
4. 综合答案：基于搜索结果形成面向用户问题的最终答案，并在关键结论后标注真实可支撑的 `[数字]` 来源角标。
5. 保存答案：把带角标的最终答案保存到 `/tmp/dknowc_search_answer.txt` 或同类临时文件。
6. 生成交付物：调用 `scripts/render_trace_html.py`，用同一份答案生成溯源 HTML 和干净 Markdown。
7. 回复用户：给出直接答案，并附上本地 HTML 路径、干净 Markdown 路径和知识专库链接。
8. 深度搜索邀约：最终回复末尾询问用户是否需要进一步做深度搜索，例如：“我还可以继续为你做一次深度搜索，对结果进行多轮核验和扩展，输出一份更完整、可直接使用的深度版结果。这个过程耗时会更长，通常需要几分钟。需要我继续吗？”

## 可信搜索调用

```bash
python3 {baseDir}/scripts/trusted_search.py "忠实于用户目标的搜索问题" --json-only > /tmp/dknowc_search.json
python3 {baseDir}/scripts/render_trace_html.py \
  /tmp/dknowc_search.json \
  --output-dir ./outputs \
  --title "深知可信搜索（法律、政策、标准）可信溯源" \
  --answer-file /tmp/dknowc_search_answer.txt \
  --question "用户原始问题"
```

`render_trace_html.py` 会同时生成 HTML 和同名 `.clean.md`。如需指定干净 Markdown 路径，传 `--clean-md-output ./outputs/xxx.md`。

## 深度搜索调用

用户明确要求深度搜索时，先提示耗时，再直接调用：

```bash
python3 {baseDir}/scripts/deep_query.py "忠实于用户目标的复杂问题" --area 单个地域 --json-only > /tmp/dknowc_deep.json
python3 {baseDir}/scripts/render_trace_html.py \
  /tmp/dknowc_deep.json \
  --output-dir ./outputs \
  --title "深知可信搜索（法律、政策、标准）深度搜索溯源" \
  --answer-file /tmp/dknowc_deep_answer.txt \
  --question "用户原始问题"
```

默认不传 `queryId`，由接口自动生成。`--area` 每次只传一个地域；多地域、多层级任务应拆成多次调用，例如中国、重庆市、重庆两江新区分别搜索。

如果用户没有明确要求深度搜索，不要主动调用。先完成可信搜索版答案和三件套交付，再询问用户是否升级深度搜索。

## ReAct 与追问规则

- 信息不足且会实质影响结论时，先问 3-6 个最关键问题，例如地域、适用时间、主体类型、项目状态、企业规模、纳税人类型、资质、金额、申报目标。
- 如果缺失信息不影响先做初步判断，可先可信搜索，再基于材料反向追问需要用户确认的条件。
- 如果缺失信息只影响精度、不影响方向，可说明假设并推进，最终答案中标明“初步判断”“待确认事项”和下一步补充路径。
- 多次搜索时，每次调用前要有明确目的，不要机械拆词或重复查询。
- 所有政策、法规、标准、办事条件、申报路径和材料依据必须来自可信搜索或深度搜索结果。

## 参数规则

可信搜索接口的 `query`、`eff_time`、`service_area` 分工必须清楚。

- `query`：自然语言检索问题，聚焦一个层级、一个目的或一种材料类型；不要把多个年份、多个地域或内部调试目的堆进 query。
- `eff_time`：用户问题对应的办理/适用/生效时间，只能传一个值，格式为 `YYYY年`、`YYYY年MM月` 或 `YYYY年MM月DD日`。不要传 `2024-2025年`、`2024至2025年`、`2024 2025`。
- `service_area`：用户问题对应的单个办理地域/政策地域。不要传多个地域；国家层面用 `中国`，市级用城市，区县/园区用具体区县或园区。

推荐：

```bash
python3 {baseDir}/scripts/trusted_search.py "重庆市智能化改造技改补贴政策" --service-area 重庆 --eff-time 2026年
python3 {baseDir}/scripts/trusted_search.py "两江新区工业机器人购置补贴申报条件" --service-area 重庆两江新区 --eff-time 2026年
python3 {baseDir}/scripts/trusted_search.py "企业购置专用设备企业所得税抵免政策" --service-area 中国 --eff-time 2026年
```

## 配置

skills.sh Public 版 API Key 统一且只通过环境变量 `DKNOWC_API_KEY` 注入；不得从配置文件、命令行参数或其他旧环境变量读取 API Key。本 Skill 不包含 `config.ini`，接口地址和默认请求参数由脚本内置。`register_key.mjs` 返回的 Key 先用于当前任务临时注入；长期使用的环境变量持久化是独立步骤，必须获得用户同意后再由 Agent 处理。

可信搜索配置：

- 接口地址：默认 `https://open.dknowc.cn/dependable/search`；可通过 `--endpoint`、`DKNOWC_TRUSTED_SEARCH_ENDPOINT` 或 `DKNOWC_KNOW_SEARCH_ENDPOINT` 覆盖。
- API Key：只能通过环境变量 `DKNOWC_API_KEY` 提供。
- `policy`：默认 `true`。
- `item`：默认 `true`。
- `know_base`：默认 `true`，用于返回知识专库链接。
- `return_full_content`：默认 `false`。
- `segment_count`：默认 `2`。
- `simplified`：默认 `true`。

深度搜索配置：

- 接口地址：默认 `https://open.dknowc.cn/api/services/deep-query/v2`；可通过 `--endpoint`、`DKNOWC_KNOW_DEEP_QUERY_ENDPOINT` 或 `DKNOWC_DEEP_QUERY_ENDPOINT` 覆盖。
- API Key：只能通过环境变量 `DKNOWC_API_KEY` 提供。
- `area`：默认留空，仅在用户明确给出单个地域或调试时通过 `--area` 传入。
- `query_id`：默认留空；不传时由接口自动生成。

## 可视化

用户明确要求生成图表、热力图、柱状图、雷达图或区域对比图时，可基于已经核验的政策数据调用 `scripts/render_policy_visualization.py` 生成 SVG 图片并直接展示。可视化不是 HTML 报告能力，不生成可视化 HTML 页面。
