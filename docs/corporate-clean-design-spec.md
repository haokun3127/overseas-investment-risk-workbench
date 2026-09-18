# 企业简洁风 设计规范

style_slug: corporate-clean

## 什么时候用
- 实现前需要统一团队或 AI 对这个风格的理解时使用。
- 把任务交给 AI 前，用它确定颜色、布局、组件、动效和可访问性的边界。
- 审核结果时，用它判断生成界面是否仍然属于这个风格。

## 怎么用
- 先读"概览"和"视觉系统"，理解这个风格的识别点。
- 把"布局规则"和"组件规则"当作实现边界。
- 交付前按"交付检查"逐条自检。

## 概览
专业简洁的企业风格，强调可读性、一致性和信任感。适合B2B SaaS、企业官网、后台管理系统。

## 设计意图
Corporate Clean 设计风格源于现代企业软件的设计语言，强调专业性、可信度和高效的信息传达。

## 视觉系统
- Primary: #1e40af
- Secondary: #f8fafc
- Accents: #3b82f6, #64748b, #10b981, #c559f0
- Signature cues: 企业、专业、简洁、B2B、SaaS、后台、Dashboard、minimal

## 布局规则
- 区块节奏：`py-12 md:py-16 lg:py-20`
- 容器内边距：`px-4 md:px-6 lg:px-8`
- 卡片内边距：`p-6`
- 默认间距：`gap-6`
- 圆角：`rounded-lg`

## 组件规则
- 使用 rounded-lg 或 rounded-xl 作为主要圆角
- 按钮使用 shadow-sm 增加层次感
- 主色使用蓝色系 (blue-600, blue-700) 传达专业感
- 背景使用 bg-slate-50 或 bg-gray-50 的浅色调
- 卡片使用 bg-white shadow-sm border border-gray-200
- 按钮 hover 时轻微上浮 hover:-translate-y-0.5 + 阴影微升 hover:shadow
- 按钮 active 时轻微缩小 active:scale-[0.98] 传达"已按下"的触觉确认
- 焦点状态使用 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2（ring-offset 是 WCAG 合规关键）

## 交互与动效
- 过渡：`transition-all duration-200`
- 悬停：`hover:shadow-md`
- 按下：`active:scale-95`
- 聚焦：`ring-2 ring-blue-500`
- 动效不得引发布局位移或抢走焦点。

## 可访问性
- 文字对比度保持 WCAG AA 或更高。
- 每个可交互元素都必须保留清晰键盘焦点。
- 移动端触控目标不低于 44px，并尊重 reduced-motion。

## 禁止项
- 禁止使用过于鲜艳的颜色组合
- 禁止使用 rounded-none 的尖锐边角
- 禁止使用渐变按钮（保持扁平设计）
- 禁止在正文中使用花哨字体
- 禁止元素间距过于紧凑
- 禁止使用超过 duration-200 的动画（企业 UI 要利落，不要飘逸）
- 禁止 focus:ring 缺少 focus:ring-offset-2（ring-offset 让焦点环与元素分离，符合 WCAG）
- 禁止按钮缺少 active:scale-[0.98]（没有按压反馈，按钮像装饰品）

## 交付检查
- 替换示例内容后，页面仍应一眼识别为 企业简洁风。
- 按钮、卡片、输入、空状态、错误、加载状态应共享同一套视觉语言。
- 上面"禁止项"里的任何一条都没有被通用组件库的默认样式带进来。