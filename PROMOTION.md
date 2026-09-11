# 深知可信搜索 GitHub Public 发布说明

仓库地址：

https://github.com/dylanzhangzx/dknowc-trusted-search

## 简介

深知可信搜索（法律、政策、标准）是基于深知可信智能提供的可信搜索与权威材料检索 Agent Skill，面向政策法规、政务办事依据、税务社保、公积金、企业补贴、资质证照、行业标准、公共服务、合规义务、政策调研、城市政策对比和企业投资/技改/税惠材料核验等工作场景。默认调用可信搜索接口，按用户明确要求调用深度搜索接口，最终交付直接回复答案、可点击溯源 HTML 和移除来源角标的干净 Markdown，所有材料来源可溯源、可核验。

本 GitHub Public 版采用 skills.sh 渠道配置，不内置深知搜索 API Key。首次调用时必须先确认环境变量 `DKNOWC_API_KEY` 已配置；未配置时，Agent 可先通过 MaaS 手机号验证码流程获取 Key，让当前任务临时继续执行；持久化环境变量是独立步骤，必须在用户明确同意后再处理。

## GitHub Release 文案

Title:

v1.2.1 - GitHub public release

Body:

This is the skills.sh GitHub public release of 深知可信搜索, an Agent Skill for trusted search and authoritative-source retrieval covering policy, regulation, government-service evidence, standards, compliance, subsidy, tax-benefit and policy research tasks.

Highlights:

- Uses the skills.sh channel configuration.
- Defaults to trusted search (`scripts/trusted_search.py`); deep search (`scripts/deep_query.py`) is only used on explicit user request or confirmation.
- Delivers a three-piece output: a direct answer, clickable provenance HTML, and clean Markdown with source markers removed (`scripts/render_trace_html.py`).
- Generates interactive policy-visualization HTML reports on request, with optional `--svg` static snapshots (`scripts/render_policy_visualization.py`).
- API Key is injected only through the environment variable `DKNOWC_API_KEY`; the Skill does not include a local `config.ini` and does not contain any real API Key.
- No unified consulting interface: the Skill no longer calls `gov_chat.py`.
- v1.1.1 unified the Skill workspace: intermediate artifacts and deliverables land under `official-docs/` inside the Skill directory (no more `/tmp` or top-level `outputs/`); `trusted_search.py`/`deep_query.py` gained `--output/-o` to write result JSON natively to `official-docs/search-results/`.
- v1.1.2 upgrades visualization to interactive self-contained HTML reports (primary deliverable) with per-data-point `sources` provenance binding and hover/click source popups, keeping `--svg` static snapshots for in-chat display. Unifies the visualization JSON schema (`metadata` + explicit `metrics` + `items`, backward compatible) with four scenarios (`city_compare`, `amount_compare`, `process_steps`, `timeline`); metrics engine prefers an explicit schema and falls back to auto-detection with an "auto-口径" note. HTML reports embed CSS/JS locally (no CDN, no external fonts), fully offline-capable.
- v1.1.3 optimizes the onboarding flow for enabling trusted retrieval: value-first, timing-deferred phone-verification guidance with a graceful fallback (model-knowledge answers flagged "依据待核验" when the user declines), plus a light post-delivery hint (at most once per task). Adds a `reference/` folder with capability talking points (`search_intro.md`) and sample outputs (`sample_search_result.md`, `sample_trace_report.html`) for demonstrating retrieval quality; samples are display-only and never shipped as deliverables. `register_key.mjs` now carries the channel code on both the sendMessage and register request bodies for channel-level registration analytics.
- v1.2.1 hardens the registration funnel with fixed scripts and auto-persists the API key: new `reference/onboarding_scripts.md` fixed-script library (S1 value/rights-first pitch with 300 free queries + 100 CNY identity-verification credit, S2 phone ask with full safety boundaries, S3/S4/S5 sent/wrong-code/success scripts, S6 runtime questions; error-response table; FAQ; no-fabrication-before-confirmation rules) replaces the free-form `search_intro.md`. `register_key.mjs` now emits `user_message` on every branch (masked phone), auto-writes the key into a `~/.zshrc` marker block (idempotent, 0600, `--no-zshrc` to skip — no host restart needed), and falls back to the existing key when new-key creation fails. `trusted_search.py`/`deep_query.py` emit structured error JSON (`quota_exhausted`, `retry_forbidden`, `user_message`; 402/429 quota exhaustion forbids retries; 401 re-reads the key once). Platform URL unified to the login page.
- v1.2.0 adds API Key zshrc fallback: new `scripts/api_key.py` resolves the key from the process env first, then from `~/.zshrc` when the host process can't see shell exports (WorkBuddy 5.5.3 no longer falsely reports a missing key; no host restart needed). `initialize.py` accepts `api_key_source` of `environment` or `zshrc`; caller scripts fall back in sync. The verification report is rebranded to "溯源核验报告" with document-header identity stamp, humanized metric names, per-material cards (multi-segment merged — fixes citation semantics when one article was split into many cards), high-trust gold badges, retrieval-group filtering, and a mobile side-by-side excerpt comparison overlay; renderer is 1:1 with the official-doc-writer 3.6.0 rendering layer. `category` fixed to `office-efficiency` (platform enum slug).
- v1.1.6 tightens citation-mounting discipline and targeted follow-up search (from WorkBuddy A/B testing): citations must land on materials that directly carry the clause's original text (the click-through excerpt must substantiate the sentence); multi-source conclusions are split and cited separately; specific conditions/numbers/procedures may never be cited to topically-related materials that lack the clause. When the user's core ask is a specific number (amount/ratio/deadline/multiplier) and the first round returns only framework content, a targeted follow-up query ("管理办法/实施细则/办理指南/区县名") is mandatory before answering. Self-check items ① and ⑤ refined accordingly.
- v1.1.5 upgrades the trace report into a verification report: report-level verification sheet with five metrics (evidence traceability, citation binding, freshness, type coverage, answer self-check via `--self-check-file`), citations renumbered by first appearance, verification scoped to cited materials only (knowledge-base-viewable counts as verifiable), "verified" as the default delivery state, and hard pre-generation checks (refuses to render when the answer lacks `[n]` citations or bindings). New report-style layout with sectioned answer cards, four-way material color coding, print mode and mobile adaptation. Adds `scripts/deliver_outputs.py` to copy fresh deliverables into the host workspace before replying.
- v1.1.4 upgrades the deep-search API from deep-query/v2 to v3: non-streaming (one POST returns the full JSON, SSE line-merging removed), request field `question` renamed to `query`, `areas` accepts multiple regions in one call (server splits into per-region sub-queries), and responses expose `data.searches` (per-sub-query grouped materials), `data.common_articles` (shared articles) and `traceId` for tracing. `render_trace_html.py` now parses the v3 format only (dedup by source URL) with the v2 events/data.list branches removed.

Users can manage MaaS usage at https://platform.dknowc.cn/.

## 推荐 GitHub Topics

```text
agent-skills
skills-sh
trusted-search
ai-search
policy-research
legal-search
document-retrieval
official-documents
dknowc
```
