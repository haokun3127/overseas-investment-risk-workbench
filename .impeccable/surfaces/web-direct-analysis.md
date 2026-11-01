---
version: 1
slug: "web-direct-analysis"
primary_target: "web/app.js"
related_targets: ["web/companies.js", "web/evidence.js", "web/websearch.js", "web/workflows.js", "web/features.js"]
---

# 资料直接分析 — 已实现的范围说明

## Mode and intent

Operate：业务人员上传或录入风险资料后直接进入后台分析队列，知识资料进入检索及中文摘要处理范围。本次只记录逐项外部 AI 授权的移除与直接导入流程；沿用现有工作台，不改变分级对策参考的范围说明，也不更新 PRODUCT.md 中其他历史断言。

## Direction contract

- Thesis：以资料用途与实际任务状态组织流程，减少导入前的逐项选择。
- Own world：保留玄墨导航、纸白表面、潮汐青操作、本机中文字体和现有控件。
- Story：选择上传或录入 → 保存资料 → 风险资料自动入队 / 知识资料供检索与摘要 → 查看进度、原文和分析历史。
- First viewport：现有列表、用途导航与导入入口；移除授权列、数量、筛选、徽章及详情授权设置。
- Form：桌面沿用资料列表和导入区域，手机沿用纵向表单与资料行，不新增 CSS 或装饰。
- Finish：引用已完成的 scoped UI review，结论为 ship，无实质界面问题。

## Implemented behavior and boundaries

文件与手动表单均以“导入并分析资料”提交风险资料；保存后自动请求后台任务，无授权或自动分析复选框。知识表单为“导入知识库”，后续检索与中文摘要仍依赖现有处理条件。保存中禁用提交按钮，导入结果沿用现有反馈区域和提示；任务列表继续显示排队、运行、失败、取消及重新分析。模型配置或规则条件不足时，资料保留并说明未启动原因，不把入队或保存写成模型分析完成。

公司背景、补充材料和网站来源不再以旧逐项授权字段限制使用；旧字段为兼容保留，不作为分析、摘要或检索准入条件。企业归属与登录、隔离、演示限制、模型配置、规则检查及去重继续有效。已有模型结果和版本保留，不因取消授权自动重跑。补证重新分析仍为原有显式操作；网站启停、调度、自动入库及自动分析设置继续控制其独立工作流程。

## Implementation sources

- `web/app.js`：资料/知识列表、导入表单、文字与文件保存后的风险任务提交、原文弹窗；清除旧授权筛选。
- `web/companies.js`：公司表单与背景说明。
- `web/evidence.js`：补充材料表单及分析路径。
- `web/websearch.js`：单个与批量网站来源配置；保留网站运行设置。
- `web/workflows.js`、`web/features.js`：相关流程及说明；历史分析、原文定位和业务复核继续沿用。

## Verification record

功能边界见 `docs/DIRECT-ANALYSIS.md`；界面复核见 `docs/DIRECT-ANALYSIS-UI-REVIEW.md`，`disposition: ship`。本记录引用该复核及其证据，不声称重新执行浏览器、检测器或模型测试。

证据目录为 `../rag-original-rules-audit-20261101/ui-direct-analysis-round1/`：`documents-desktop.png`、`documents-rows-mobile.png`、`knowledge-rows-mobile.png`、`manual-import-mobile.png`、`source-mobile.png` 与 `verification.json`。隔离样例关闭分析工作线程，验证文字和文件无需复选框即可入队、旧筛选失效、列表对齐、手机无横向溢出和详情授权表单移除。该证据不表示真实配置模型已完成分析；键盘/辅助技术、次要表单与所有异常状态未独立运行验证。

本次仅追加范围文档，保留既有 DESIGN.md 历史、`.impeccable/design.json` 与分级对策 surface brief。
