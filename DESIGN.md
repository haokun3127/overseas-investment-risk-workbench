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
