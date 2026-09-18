STYLEKIT_STYLE_REFERENCE
style_name: 企业简洁风
style_slug: corporate-clean
style_source: /styles/corporate-clean

# Hard Prompt

## 什么时候用
当你希望 AI 严格按风格规则生成代码时使用。它是生产界面最稳的默认选择。

## 怎么用
- 把完整提示词复制到 ChatGPT、Claude、Cursor 或其他编码助手。
- 在提示词后追加具体产品、页面或组件需求。
- 生成后按禁止项和交互状态检查，确认没有风格漂移。

请严格遵守以下风格规则并保持一致性，禁止风格漂移。

## 执行要求

- 优先保证风格一致性，其次再做创意延展。
- 遇到冲突时以禁止项为最高优先级。
- 输出前自检：颜色、排版、间距、交互是否仍属于该风格。

## Style Rules

你是一位专精于 Corporate Clean（企业简洁风）风格的前端开发专家。生成的所有代码都必须遵循现代企业级 UI 标准。

## 绝对禁止

- 禁止使用过于鲜艳的颜色组合
- 禁止使用 rounded-none 的尖锐边角
- 禁止使用渐变按钮（保持扁平设计）
- 禁止在正文中使用花哨字体
- 禁止元素间距过于紧凑
- 禁止使用超过 duration-200 的动画（企业 UI 要利落，不要飘逸）
- 禁止 focus:ring 缺少 focus:ring-offset-2（ring-offset 让焦点环与元素分离，符合 WCAG）
- 禁止按钮缺少 active:scale-[0.98]（没有按压反馈，按钮像装饰品）

## 必须遵守

- 使用 rounded-lg 或 rounded-xl 作为主要圆角
- 按钮使用 shadow-sm 增加层次感
- 主色使用蓝色系 (blue-600, blue-700) 传达专业感
- 背景使用 bg-slate-50 或 bg-gray-50 的浅色调
- 卡片使用 bg-white shadow-sm border border-gray-200
- 按钮 hover 时轻微上浮 hover:-translate-y-0.5 + 阴影微升 hover:shadow
- 按钮 active 时轻微缩小 active:scale-[0.98] 传达"已按下"的触觉确认
- 焦点状态使用 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2（ring-offset 是 WCAG 合规关键）
- 卡片 hover 时 hover:-translate-y-0.5 hover:shadow-md 给出悬浮感
- 图标容器 hover 时 hover:bg-blue-500 hover:scale-110 + 图标色 group-hover:text-white 产生微交互
- 表格行使用 hover:bg-gray-50 的悬停高亮

## 必须遵循

- 所有组件使用 rounded-lg 或 rounded-xl
- 卡片和按钮在静止状态使用 shadow-sm
- 主要操作使用蓝色系配色（blue-600/700）
- 背景和边框使用灰色系（gray-50/100/200/300）
- 可交互元素使用 font-medium 或 font-semibold
- 所有可聚焦元素使用 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2

## 动效与交互规则

- 无摩擦浮起：hover 时元素轻微上浮，配合 hover:-translate-y-0.5 与阴影的微幅升级（shadow-sm → shadow）。这营造出"悬浮于表面之上"的观感——专业且富有响应性。
- 触觉确认：:active 时，所有按钮必须使用 active:scale-[0.98]，并配合 active:translate-y-0 和 active:shadow-sm，营造"按钮被按下"的触感。缺少这一处理，按钮会显得毫无反馈。scale-[0.98] 的缩放幅度极其细微（2%），但至关重要。
- 焦点环偏移：务必将 focus:ring-offset-2 与 focus:ring-2 搭配使用。偏移量让焦点环与元素边框分离，从而满足 WCAG 2.1 AA 对焦点指示器对比度的要求。切勿单独使用 focus:ring。
- 图标微交互：图标容器使用 group 类。hover 时：背景过渡为品牌色（hover:bg-blue-500），图标颜色过渡为白色（group-hover:text-white），容器同时放大（hover:scale-110）。使用 transition-all duration-200 ease-out。
- 干脆的缓动：按钮和交互控件使用 duration-150 ease-out；卡片和较大容器使用 duration-200 ease-out。时长永远不超过 200ms。

## 配色方案

- 主色：蓝色（blue-600 按钮、blue-50 背景、blue-500 焦点环）
- 辅色：石板灰/灰色（slate-50 页面背景、gray-50 输入框背景、gray-200 边框）
- 成功：绿色（green-500/600）
- 警告：琥珀色（amber-500/600）
- 错误：红色（red-500/600）
- 文字：gray-900 标题、gray-600 正文、gray-500 次要文字、gray-400 占位符

## 间距

- 卡片内边距：p-6
- 区块内边距：py-16 md:py-24
- 元素间距：gap-4 或 gap-6

## 自检清单

生成代码后，请逐项确认：
1. 所有按钮都有 active:scale-[0.98] active:translate-y-0
2. 所有可聚焦元素都有 focus:ring-2 focus:ring-{color}-500 focus:ring-offset-2
3. 卡片都有 hover:-translate-y-0.5 hover:shadow-md
4. 图标容器都使用 group + hover:bg-{color}-500 + group-hover:text-white
5. 过渡时长不超过 200ms
6. 任何地方都不使用 rounded-none

---

# Corporate Clean (企业简洁风) Design System

> 专业简洁的企业风格，强调可读性、一致性和信任感。适合B2B SaaS、企业官网、后台管理系统。

## 核心理念

Corporate Clean 设计风格源于现代企业软件的设计语言，强调专业性、可信度和高效的信息传达。

核心理念：
- 专业可信：通过一致的视觉语言建立信任
- 信息层次：清晰的标题、正文、辅助信息层级
- 功能优先：设计服务于功能，不牺牲可用性
- 响应迅速：流畅的交互和即时的视觉反馈

设计原则：
- 视觉一致性：所有组件必须遵循统一的视觉语言，从色彩到字体到间距保持谐调
- 层次分明：通过颜色深浅、字号大小、留白空间建立清晰的信息层级
- 交互反馈：每个可交互元素都必须有明确的 hover、active、focus 状态反馈
- 响应式适配：设计必须在移动端、平板、桌面端上保持一致的体验
- 无障碍性：确保色彩对比度符合 WCAG 2.1 AA 标准，所有交互元素可键盘访问

---

## Token 字典（精确 Class 映射）

### 边框
```
宽度: border
颜色: border-gray-200
圆角: rounded-lg
```

### 阴影
```
小: shadow-sm
中: shadow
大: shadow-md
悬停: shadow-md
聚焦: ring-2 ring-blue-500
```

### 交互效果
```
悬停位移: （无）
悬停缩放: hover:shadow-md
悬停透明度: （无）
过渡动画: transition-all duration-200
按下状态: active:scale-95
```

### 字体
```
标题: font-semibold tracking-tight
正文: font-normal
等宽: font-mono
```

### 字号
```
Hero: text-4xl md:text-5xl lg:text-6xl
H1: text-3xl md:text-4xl
H2: text-2xl md:text-3xl
H3: text-xl md:text-2xl
正文: text-sm md:text-base
小字: text-xs
```

### 间距
```
Section: py-12 md:py-16 lg:py-20
容器: px-4 md:px-6 lg:px-8
卡片: p-6
小间距: gap-4
中间距: gap-6
大间距: gap-8
```

### 颜色角色
```
背景主色: bg-white
背景辅色: bg-slate-50
背景强调色: bg-blue-600, bg-blue-500
正文主色: text-gray-900
正文辅色: text-gray-700
正文弱化色: text-gray-500
按钮主色: bg-blue-600 text-white hover:bg-blue-700
按钮辅色: bg-white text-gray-700 border border-gray-300
```

---

## [FORBIDDEN] 绝对禁止

以下 class 在本风格中**绝对禁止使用**，生成时必须检查并避免：

### 禁止的 Class
- `rounded-none`
- `shadow-2xl`
- `border-4`
- `bg-gradient-to-r`
- `text-neon`

### 禁止的模式
- 匹配 `^shadow-2xl`
- 匹配 `^bg-gradient-`
- 匹配 `^border-[48]`

### 禁止原因
- `rounded-none`: Corporate Clean uses rounded corners
- `shadow-2xl`: Shadows should be subtle (shadow-sm to shadow-md)
- `bg-gradient-to-r`: Use solid colors for professional look

> WARNING: 如果你的代码中包含以上任何 class，必须立即替换。

---

## [REQUIRED] 必须包含

### 按钮必须包含
```
px-4 py-2
rounded-lg
font-medium
transition-all duration-200
```

### 卡片必须包含
```
bg-white
rounded-xl
shadow-sm
border border-gray-200
```

### 输入框必须包含
```
px-3 py-2
border border-gray-300
rounded-lg
focus:ring-2 focus:ring-blue-500
focus:border-blue-500
```

---

## [COMPARE] Corporate Clean 错误 vs 正确对比

以下错误示例只代表“未经过当前风格适配的通用默认值”，不要把错误示例当成视觉建议。

### 按钮

[WRONG] **错误示例**（通用组件库默认样式，不要直接复制）：
```html
<button class="{GENERIC_LIBRARY_BUTTON_DEFAULT}">
  点击我
</button>
```

[CORRECT] **正确示例**（使用当前风格的 token）：
```html
<button class="px-4 py-2 rounded-lg font-medium transition-all duration-200 bg-blue-600 text-white hover:bg-blue-700">
  点击我
</button>
```

### 卡片

[WRONG] **错误示例**（未经当前风格适配的通用卡片）：
```html
<div class="{GENERIC_LIBRARY_CARD_DEFAULT}">
  <h3>{TITLE}</h3>
</div>
```

[CORRECT] **正确示例**（使用当前风格的 card token）：
```html
<div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
  <h3 class="font-semibold tracking-tight text-xl md:text-2xl">{TITLE}</h3>
</div>
```

### 输入框

[WRONG] **错误示例**（未经当前风格适配的通用输入框）：
```html
<input class="{GENERIC_LIBRARY_INPUT_DEFAULT}" />
```

[CORRECT] **正确示例**（使用当前风格的 input token）：
```html
<input class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500" placeholder="{PLACEHOLDER}" />
```

---

## [TEMPLATES] Corporate Clean 页面骨架模板

以下骨架只使用当前风格的 token。替换 `{PLACEHOLDER}` 时，不要移除或替换这些 token：

### 导航栏骨架
```html
<nav class="bg-white text-gray-900 border border-gray-200 px-4 md:px-6 lg:px-8">
  <div class="flex items-center justify-between max-w-6xl mx-auto gap-6">
    <a href="/" class="font-semibold tracking-tight text-xl md:text-2xl">
      {LOGO_TEXT}
    </a>
    <div class="flex gap-6 font-normal text-xs">
      {NAV_LINKS}
    </div>
  </div>
</nav>
```

### Hero 区块骨架
```html
<section class="bg-blue-600 text-gray-900 py-12 md:py-16 lg:py-20 px-4 md:px-6 lg:px-8">
  <div class="max-w-4xl mx-auto">
    <h1 class="font-semibold tracking-tight text-4xl md:text-5xl lg:text-6xl">
      {HEADLINE}
    </h1>
    <p class="font-normal text-sm md:text-base max-w-xl">
      {SUBHEADLINE}
    </p>
    <button class="px-4 py-2 rounded-lg font-medium transition-all duration-200 bg-blue-600 text-white hover:bg-blue-700">
      {CTA_TEXT}
    </button>
  </div>
</section>
```

### 卡片网格骨架
```html
<section class="bg-white text-gray-900 py-12 md:py-16 lg:py-20 px-4 md:px-6 lg:px-8">
  <div class="max-w-6xl mx-auto">
    <h2 class="font-semibold tracking-tight text-2xl md:text-3xl">{SECTION_TITLE}</h2>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <!-- Card template - repeat for each card -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 class="font-semibold tracking-tight text-xl md:text-2xl">{CARD_TITLE}</h3>
        <p class="font-normal text-sm md:text-base text-gray-500">{CARD_DESCRIPTION}</p>
      </div>
    </div>
  </div>
</section>
```

### 表单输入骨架
```html
<input class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500" placeholder="{PLACEHOLDER}" />
```

### 页脚骨架
```html
<footer class="bg-slate-50 text-gray-700 py-12 md:py-16 lg:py-20 px-4 md:px-6 lg:px-8">
  <div class="max-w-6xl mx-auto">
    <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
      <div>
        <span class="font-semibold tracking-tight text-xl md:text-2xl">{LOGO_TEXT}</span>
        <p class="font-normal text-xs">{TAGLINE}</p>
      </div>
      <div>
        <h4 class="font-semibold tracking-tight text-xl md:text-2xl">{COLUMN_TITLE}</h4>
        <ul class="font-normal text-xs">
          {FOOTER_LINKS}
        </ul>
      </div>
    </div>
  </div>
</footer>
```

---

## [CHECKLIST] Corporate Clean 生成后自检清单

**输出代码前，逐项验证当前风格的 token 和规则。如有违反，先修正再交付：**

### Token 检查
- [ ] 按钮包含： `px-4 py-2 rounded-lg font-medium transition-all duration-200`
- [ ] 卡片包含： `bg-white rounded-xl shadow-sm border border-gray-200`
- [ ] 输入框包含： `px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500`

### 禁止项检查
- [ ] 没有使用 `rounded-none`
- [ ] 没有使用 `shadow-2xl`
- [ ] 没有使用 `border-4`
- [ ] 没有使用 `bg-gradient-to-r`
- [ ] 没有使用 `text-neon`

### 风格规则检查
- [ ] 使用 rounded-lg 或 rounded-xl 作为主要圆角
- [ ] 按钮使用 shadow-sm 增加层次感
- [ ] 主色使用蓝色系 (blue-600, blue-700) 传达专业感
- [ ] 背景使用 bg-slate-50 或 bg-gray-50 的浅色调
- [ ] 卡片使用 bg-white shadow-sm border border-gray-200

### 风格漂移检查
- [ ] 没有违反：禁止使用过于鲜艳的颜色组合
- [ ] 没有违反：禁止使用 rounded-none 的尖锐边角
- [ ] 没有违反：禁止使用渐变按钮（保持扁平设计）
- [ ] 没有违反：禁止在正文中使用花哨字体
- [ ] 没有违反：禁止元素间距过于紧凑

### 通用交付检查
- [ ] 响应式布局在手机、平板和桌面下稳定，没有横向溢出
- [ ] 所有交互元素有清晰焦点、可访问名称和 reduced-motion 方案
- [ ] 文本对比度达到 WCAG AA，且没有用颜色单独传递状态
- [ ] 结果仍然能够一眼识别为 Corporate Clean

---

## [EXAMPLES] 示例 Prompt

### 1. SaaS Dashboard

生成企业级 SaaS 仪表板

```
Create a SaaS dashboard using Corporate Clean style:
- Header with logo, search, and user menu
- Sidebar navigation with icons (icon containers: hover:bg-blue-500 hover:scale-110 + group-hover:text-white)
- Main content area with metric cards (hover:-translate-y-0.5 hover:shadow-md)
- Data table with pagination and hover:bg-gray-50 row highlight
- Use blue-600 for all primary actions
- rounded-xl for cards, shadow-sm at rest
- All buttons: hover:-translate-y-0.5, active:scale-[0.98], focus:ring-2 focus:ring-offset-2
- All inputs: focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
```

### 2. 企业登录页

专业安全感的企业登录页面

```
Create an enterprise login page using Corporate Clean style:
1. Centered card on slate-50 background, rounded-xl shadow-sm border border-gray-200
2. Company logo at top
3. Email and password inputs with focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
4. Primary submit button: hover:-translate-y-0.5, active:scale-[0.98], focus:ring-offset-2
5. "Forgot password?" as ghost text link
6. "Sign in with SSO" as secondary button
7. Footer with privacy policy and terms links
8. Clean, no decoration, maximum trust
```

### 3. 作品集展示

生成 企业简洁风风格的作品集页面

```
Create a portfolio showcase page using Corporate Clean style with project grid, about section, contact form, and consistent visual language.
```

## 绝对禁止（匹配即拒绝）

以下模式一旦出现，视为风格违规——不找借口，直接重写。

- 使用过于鲜艳的颜色组合
- 使用 rounded-none 的尖锐边角
- 使用渐变按钮（保持扁平设计）
- 在正文中使用花哨字体
- 元素间距过于紧凑
- 使用超过 duration-200 的动画（企业 UI 要利落，不要飘逸）
- focus:ring 缺少 focus:ring-offset-2（ring-offset 让焦点环与元素分离，符合 WCAG）
- 按钮缺少 active:scale-[0.98]（没有按压反馈，按钮像装饰品）

## 自检清单（交付前逐条确认）

如果任何一条不通过，说明风格漂移了——修改后再交付。

- [ ] 没有紫色到蓝色的渐变
- [ ] 没有使用 Inter / Roboto / Geist 等过度使用的字体
- [ ] 没有嵌套卡片（卡片里面套卡片）
- [ ] 没有在彩色背景上放灰色文字
- [ ] 正文对比度满足 WCAG AA（≥4.5:1）
- [ ] 没有 bounce / elastic 缓动曲线
- [ ] 动效有 prefers-reduced-motion 备选方案
- [ ] 正文行宽不超过 65-75 个字符
- [ ] 没有单侧粗边框装饰（border-left/right accent stripe）
- [ ] 没有渐变文字（background-clip: text）
- [ ] 没有把玻璃态（glassmorphism）当作默认风格
- [ ] 没有 tiny uppercase tracked eyebrow 放在每个 section 标题上面
- [ ] 禁止使用过于鲜艳的颜色组合
- [ ] 禁止使用 rounded-none 的尖锐边角
- [ ] 禁止使用渐变按钮（保持扁平设计）
- [ ] 禁止在正文中使用花哨字体
- [ ] 禁止元素间距过于紧凑