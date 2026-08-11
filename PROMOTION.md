# 深知可信搜索 GitHub Public 发布说明

仓库地址：

https://github.com/dylanzhangzx/dknowc-trusted-search

## 简介

深知可信搜索（法律、政策、标准）是基于深知可信智能提供的可信搜索与权威材料检索 Agent Skill，面向政策法规、政务办事依据、税务社保、公积金、企业补贴、资质证照、行业标准、公共服务、合规义务、政策调研、城市政策对比和企业投资/技改/税惠材料核验等工作场景。默认调用可信搜索接口，按用户明确要求调用深度搜索接口，最终交付直接回复答案、可点击溯源 HTML 和移除来源角标的干净 Markdown，所有材料来源可溯源、可核验。

本 GitHub Public 版采用 skills.sh 渠道配置，不内置深知搜索 API Key。首次调用时必须先确认环境变量 `DKNOWC_API_KEY` 已配置；未配置时，Agent 可先通过 MaaS 手机号验证码流程获取 Key，让当前任务临时继续执行；持久化环境变量是独立步骤，必须在用户明确同意后再处理。

## GitHub Release 文案

Title:

v1.1.0 - GitHub public release

Body:

This is the skills.sh GitHub public release of 深知可信搜索, an Agent Skill for trusted search and authoritative-source retrieval covering policy, regulation, government-service evidence, standards, compliance, subsidy, tax-benefit and policy research tasks.

Highlights:

- Uses the skills.sh channel configuration.
- Defaults to trusted search (`scripts/trusted_search.py`); deep search (`scripts/deep_query.py`) is only used on explicit user request or confirmation.
- Delivers a three-piece output: a direct answer, clickable provenance HTML, and clean Markdown with source markers removed (`scripts/render_trace_html.py`).
- Generates policy visualizations as SVG when requested (`scripts/render_policy_visualization.py`).
- API Key is injected only through the environment variable `DKNOWC_API_KEY`; the Skill does not include a local `config.ini` and does not contain any real API Key.
- No unified consulting interface: the Skill no longer calls `gov_chat.py`.

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
