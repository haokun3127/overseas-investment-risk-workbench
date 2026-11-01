---
version: 1
slug: "web-countermeasures-js"
primary_target: "web/countermeasures.js"
related_targets: ["web/countermeasures.css","web/features.js","web/app.js","web/index.html","web/workflows.js","web/workspace.js"]
---

# 分级对策参考 — 已实现的范围说明

## Mode and intent

Read / Operate：业务人员选择预警等级，理解对应的原文可选对策，并追溯来源。此记录只覆盖分级对策库、事件参考入口与简报附录；保留现有工作台的玄墨、纸白、潮汐青视觉世界。PRODUCT.md 中既有数据与模型断言未在此次文档工作中更新。

## Direction contract

- Thesis：把已保存预警等级与可追溯的企业、国家层面参考对策关联。
- Own world：沿用工作台字体、控件、风险徽章和纸白阅读表面。
- Story：选择等级 → 阅读标准 → 按责任方查阅可选对策 → 下载原文核对。
- First viewport：五级入口、所选标准和两类角色列表；不生成事件得分。
- Form：现有工作区内的独立索引、事件详情参考段和简报附录。
- Finish：本次已完成界面复核并记录 ship；此 brief 和 DESIGN.md 附记记录实际实现。

## Implemented behavior and boundaries

五级为红、黄、蓝、灰、绿。当前来源按等级合计企业45项、国家18项，保留原表顺序；这些是各等级条目合计，不等于63项不同措施。每项保留表格行列定位，来源提供标题、章节、版本和原始文件下载。此 brief 不收录客户原文内容。

预警标准与阈值先于对策；阈值说明明确其为文件区间。企业与国家两栏各自保留适用性/有权机构说明。事件参考按已保存等级显示，与模型针对该事件的建议分列；简报按筛选结果涉及等级各出现一次。缺失、无效或历史旧等级有明确说明，不猜测换算。读取参考不自动处置、不重跑模型、不修改案例的分类、等级、建议或证据。

## Layout and visual rules

沿用现行 ink / paper / tide CSS token 与本机中文界面字体，不以 DESIGN.md 早期蓝白头部记录替换当前界面。所选等级使用潮汐青边界、轮廓和文字标签；原生导航链接有 aria-current 和 focus-visible。正文桌面14–15px、手机对策15px；元信息和定位12px，说明13px。等级控件桌面至少46px、手机至少48px，圆角8px。

桌面五级导航同排，角色列表使用1.2:1两列与32px间隔。700px及以下，导航两列、第五项整行，角色列表单列；下载原文入口独立换行且至少44px高。事件详情中的角色始终单列。简报附录桌面并排、手机堆叠；打印使用独立的紧凑文字尺寸和分组/条目分页规则，并保留最终来源。

## Implementation sources

- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/countermeasures.js — 方向合约、索引、角色列表、来源、详情/就地入口与简报附录。
- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/countermeasures.css — 范围样式、触控高度、断点及打印规则。
- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/tokens.css — 当前字体、ink / paper / tide 色彩及基础尺度。
- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/workspace.css — 既有工作台视觉与控件。
- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/operations.css — 既有操作流程布局。
- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/features.js — 详情和简报中的参考段，与模型建议分列。
- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/app.js — 分级对策库路由。
- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/index.html — 侧栏入口与资源加载。
- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/workflows.js — 保存筛选简报返回的参考数据。
- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/workspace.js — 就地核验入口。

## Verification record

功能说明：C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/docs/GRADE-COUNTERMEASURES.md。
复核结论：C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/docs/COUNTERMEASURE-UI-REVIEW.md，disposition: ship；本次文档工作引用该结论，不另造评分。运行时键盘/辅助技术验证未在该复核中提供。

本次文档核对了以下第二轮静态证据；未生成新截图、图像或产品改动：

- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-original-rules-audit-20261101/ui-grade-actions-round2/library-lv1-desktop.png
- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-original-rules-audit-20261101/ui-grade-actions-round2/library-mobile.png
- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-original-rules-audit-20261101/ui-grade-actions-round2/report-appendix-desktop.png
- C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-original-rules-audit-20261101/ui-grade-actions-round2/report-appendix-mobile.png
