---
name: 海外投资风险工作台
description: 面向日常核验与甲方演示的浅色蓝白风险态势终端。
colors:
  canvas: "#f4f6fa"
  sidebar: "#ffffff"
  surface: "#ffffff"
  surface-raised: "#f7f9fc"
  surface-hover: "#eef4ff"
  text: "#1e293b"
  muted: "#52647c"
  subtle: "#61738a"
  primary: "#2563d9"
  primary-hover: "#194db3"
  primary-ink: "#ffffff"
  line: "#e2e7ef"
  focus: "#2563d9"
  risk-red: "#c93650"
  risk-orange: "#b75b13"
  risk-yellow: "#8a6909"
  success: "#217650"
typography:
  ui:
    fontFamily: '"Segoe UI", "Microsoft YaHei", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.65
  data:
    fontFamily: '"Bahnschrift", "Segoe UI", "Microsoft YaHei", sans-serif'
  page-title:
    fontSize: "29px"
    fontWeight: 650
    lineHeight: 1.35
    letterSpacing: "-0.025em"
  table:
    fontSize: "12px"
    lineHeight: 1.6
rounded:
  control: "7px"
  panel: "10px"
  dialog: "10px"
  chip: "5px"
spacing:
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  primary-button:
    backgroundColor: "{colors.primary}"
    hoverColor: "{colors.primary-hover}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.control}"
    minHeight: "42px"
  panel:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.line}"
    rounded: "{rounded.panel}"
  risk-network:
    backgroundColor: "#ffffff"
    accentColor: "{colors.primary}"
  focus:
    ring: "2px solid #2563d9 with 3px offset"
---

# Design System: 海外投资风险工作台

## Overview

当前生效工作区规范见 `docs/WORKSPACE-REDESIGN.md` 和 `web/workspace.css`：冷灰蓝画布 #f5f7fb、钴蓝 #2f64da、12px 面板圆角，主分析区与右侧复核区布局；风险列表提供就地核验，资料列表与导入侧栏并排。下文保留基础组件说明，冲突时以工作区规范为准。

2026-09-14：采用浅色研究工作台布局。首屏顺序为风险统计、风险分布主图、事件与业务复核，分析准备区置于其后。风险图采用冷白底、钴蓝节点和轻网格，表示风险类型与事件数量的归属，不表示因果关系。导航通过间距区分风险入口、资料与分析、系统配置；表格正文 13px，事件标题 14px，原文阅读 14px。主要面板圆角 10px，细中性边界配合轻阴影，减少蓝色边框。

这是一个面向业务人员的海外投资风险核验终端。科技感来自风险信号、数据读数、关系网络和证据定位本身，而不是装饰性发光。首屏回答三个问题：当前有哪些风险、哪些风险优先、下一步该复核什么。

## Colors

画布使用浅灰蓝 `#f5f7fb`，侧栏使用 `#f8faff`，内容面板使用 `#ffffff`，抬升层使用 `#f8fafc`。钴蓝 `#2f64da`只承担主操作、链接、数据连接线和焦点；更深的 `#2453bc`用于悬停与强调；红、橙、黄分别表示高风险、中风险和一般关注；绿色只表示已完成或本地服务状态。避免大面积高饱和色和纯装饰性 glow。

## Typography

界面使用 Microsoft YaHei UI、Microsoft YaHei、Segoe UI、sans-serif；正文 14px，页面标题 29px，表格 13px，辅助信息 11–12px。数字、进度和环图读数使用 Bahnschrift 优先的等宽感数据字体。代码和规则编辑器使用 Consolas。不加载外部字体。

## Layout

桌面使用固定侧栏、顶部状态栏和宽内容区。首屏结构为：页面标题与操作、数据范围、风险统计、风险态势网络、风险等级环图；随后展示最新事件、业务复核和准备状态。移动端侧栏进入文档流并横向滚动，图形网络切换为可读的类型列表，表格保留横向滚动，表单切换为单列。断点为 1190px、960px 和 700px。

## Elevation & Depth

面板用白色表面与细蓝灰边界表达层级，边界比阴影更重要。网络图使用点阵、轨道、连接线和中心读数表达风险关系；环图用风险语义色表达构成。对话框使用背景模糊与轻柔的蓝灰阴影，原文高亮使用黄色纸带色。避免把发光、玻璃和阴影同时铺到每个控件上。

## Shapes

内容面板使用 12px 圆角，按钮、输入和导航项使用 7px，风险徽章使用 5px。主要桌面按钮为 40px，移动端触控控件保持 44px 高度。按钮、选择框和上传区使用轻边界、微阴影和完整 hover/focus 状态，避免为了科技感改变业务人员熟悉的操作方式。

## Components

### Navigation and Status

侧栏用图标加中文标签，当前项使用蓝色文字和浅蓝底色。工作区明确展示国家、行业、本地存储和模型模式。顶部状态可进入“模型与规则”，不把“已填写配置”误写成“连接成功”。

### Risk Overview

统计卡片、风险网络、等级环图、事件表和业务复核面板组成总览。统计数字、图表节点、等级颜色和待办数量都能进入事件列表的对应筛选；演示数据始终带“虚构示例”标记。

### Evidence and Review

风险详情保留事件摘要、潜在影响、初步应对建议、判断依据、原文定位和业务复核。原文弹窗使用浅灰白阅读表面和黄色高亮，支持从引用跳转到正文位置。

### Inputs and Focus

输入控件使用白色背景、蓝灰边框和蓝色 focus ring。每个可交互元素都提供 hover、active、disabled、错误或加载反馈；键盘焦点使用 2px 焦点线加 3px offset，不依赖颜色单独传递状态。

## Motion and Responsive Behavior

按钮和导航过渡保持 150ms，表格和控件只做轻微状态变化。页面加载使用骨架线，不使用长时间入场动画。尊重 `prefers-reduced-motion`，关闭变换和过渡。移动端优先保证导入、检索、查看依据和复核操作完成。

## Do's and Don'ts

### Do

- 让科技感来自信号网络、数据读数、状态颜色和证据关系。
- 使用蓝白作为单一主操作色，风险色只表达风险语义。
- 让图表成为筛选入口，让详情页成为证据核验入口。
- 保留来源、运行模式、规则版本、虚构标记和外发授权说明。

### Don't

- 不使用霓虹渐变、装饰性粒子、无意义的发光或模拟游戏化仪表盘。
- 不把演示数据说成真实模型结果，不隐藏原文追溯和业务复核。
- 不让科技感削弱表格可读性、键盘焦点或移动端 44px 触控目标。

## 2026-10-11 网站检索与工作台优化

Taste审查后的定向优化：演示内容只保留小型“示例”标记与首页一行提示。手机高级筛选及辅助操作默认收起；事件列表在未选事件时铺满，核验面板按需出现。核验定位入口使用同一行，桌面保存区独立于可滚动正文，手机保存区固定底部。辅助正文使用12px，操作及分组标签允许13px，手机统计数字28px。可读灰阶为 #52647c / #596a81 / #586b83 / #53647c，阅读正文为 #344963，操作定位使用 #425c80；降低阴影强度，保留原有蓝色主操作与风险色语义。

沿用现有 Operate 工作台视觉。首页先显示统计与分布图，分类排行作为可切换视图，最新事件紧随分布图。网站检索按配置、AI筛选、核验入库组织，已有网站时默认收起配置表单；原文、网址、抓取时间和模型相关性依据同屏可核验。手机端使用展开菜单和纵向资料卡片，分布图采用顶部汇总、下方两列分类的布局，图中分类保留筛选入口。风险详情的阅读顺序为摘要、引用依据、复核、分析记录。13px 用于现有表格及图表辅助数据，11px 仅用于紧凑状态提示；手机输入控件使用16px字号，主要操作触控高度至少44px。

## 2026-10-11 玻璃材质升级

当前视觉以 glass.css 为最终覆盖层：蓝冰、浅薄荷背景，半透明面板、悬浮导航和顶部栏，白色高光边缘，圆润分段控件及蓝色主按钮。正文保持深蓝灰色，风险色继续表达业务等级。使用原生 CSS backdrop-filter 模拟网页玻璃材质，不依赖 Apple 平台 API。

手机模糊降低至12px；复核面板取消祖先模糊，避免固定保存栏被包含块捕获，操作栏自身保留玻璃效果。面板设置90px滚动留白，避免标题被顶部栏遮挡。无模糊支持时使用实色面板；减少透明度及高对比偏好也有降级样式。分布图仍为首页默认视图，示例标识保持轻量。

## 2026-10-24 操作流程优化

以线上10月23日的玄墨侧栏、纸白阅读区和潮汐青强调色为视觉基础；operations.css只覆盖本次工作流程调整。公司背景默认折叠，统计范围独立表达；桌面和手机均以分布图为默认视图。采集时间与页面刷新时间分开，网站工作状态进入可点击队列。核验侧栏按视口高度提供阅读空间，顶部116px留白包含玻璃栏效果；手机底部保存区继续固定。检索标题与状态标签分行，历史入库与本次筛选分别显示。

## 2026-10-24 补证与正文对比

补证沿用现有纸白与潮汐青工作区，以独立队列、原因、关联材料和版本历史组织任务。条目标题16px、正文14px、对比区标题15px、元信息12px，手机表单16px。新增/删除差异使用现有潮汐青、风险红及其浅底色，同时显示文字标签；比较的是保存正文，采集时间与存档时间明确区分。

## 2026-10-24 补证清单与更新待办

补证清单放在详情首屏，建议事项保留对应分析说明，采用后可逐项编辑、关联材料并记录准备状态；完整分析说明默认折叠。“材料已提供”不代表证据已充分。网站更新待办按待核验、已核验、已忽略组织跨站正文变化，对比、核验表单及转存操作按需展开；忽略原因和处理历史可追溯。桌面核验与转存并排，手机筛选栏与处理表单固定单列，保持16px表单字号和44px主要触控目标。

## 2026-10-24 顶部导航调整

顶部栏改为内容区域内贴顶的实底导航，取消外围间距、圆角、模糊和投影；滚动前后保持同一表面。桌面高度56px，手机52px，手机菜单抽屉紧接导航下边缘。原文定位和复核侧栏共用“导航高度 + 16px”的滚动留白，替代116px固定空隙。

## 2026-11-01 分级对策参考扩展

本次为现有工作台中的 Read / Operate 扩展，保留玄墨导航、纸白阅读表面、潮汐青链接和既有风险徽章。新增样式直接引用现行 `--paper`、`--paper-50`、`--line`、`--text-2`、`--tide-600/700`，继承中文界面字体；本节只记录该扩展，不刷新前文历史或全局 token。实现见 [countermeasures.js](C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/countermeasures.js)、[countermeasures.css](C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/countermeasures.css)，现行底层 token 见 [tokens.css](C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/web/tokens.css)。

分级对策库依次提供五级选择、所选等级的预警标准与原文阈值、企业和国家两类对策、逐项表格定位及来源下载。桌面角色列表为两列（1.2:1），间隔32px；700px及以下变为单列，等级导航变为两列并让第五项占满一行。标准正文15px、对策正文桌面14px/手机15px、定位与数量12px、说明13px；等级控件最小高度桌面46px/手机48px，手机原文下载入口至少44px。所选等级以边界和文字共同表达，原生链接保留 `aria-current` 与可见键盘焦点。

原文对策保持可选参考语气，企业适用性和国家层面有权机构说明随角色标题展示；原文阈值明确区别于事件得分。事件详情和就地核验区将原文参考与模型建议分列，简报附录按涉及等级各汇总一次，并保留角色、定位及最终来源。缺失原文或旧等级提供说明，不自动换算、采取措施、重跑模型或改写事件。功能边界见 [GRADE-COUNTERMEASURES.md](C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/docs/GRADE-COUNTERMEASURES.md)；本次界面复核结论为 `ship`，详见 [COUNTERMEASURE-UI-REVIEW.md](C:/Users/10397/Desktop/弹子石智能体_交付包/tmp/rag-customer-parity-20261101/docs/COUNTERMEASURE-UI-REVIEW.md)。
