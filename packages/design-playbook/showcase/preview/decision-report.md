# Decision Report — 企业入驻多步表单 Wizard

Scene: multi-step form wizard（onboarding 子类）
Density: console-tight（企业后台向导）
Template: 单卡向导（顶部 step indicator + 主体单步表单卡 + 底部 step actions），非 list / dashboard / detail。

## Regions（映射 spec L2）
- 顶栏：标题「企业入驻」+ 三段 StepIndicator（公司信息 / 管理员账户 / 支付方式）。
- 主体：单步表单卡（一次一步），卡片内字段纵向排列。
- 底部 step actions：左 Back（step1 隐藏）/ 右 Next 或 Submit。
- 覆盖层：submitting（提交中遮罩 + button loading）/ success（成功摘要覆盖主体）。

## Template 选择理由
- wizard 而非单页长表单：三步语义清晰、校验分步门控、支付方式联动隔离在 step3，匹配 spec L3 主链路与迁移守卫。
- 单卡而非多列：onboarding 顺序依赖强，一次聚焦一步降低认知负荷。

## Components（语义）
- **StepIndicator**：3 段；态 = 未达(disabled) / 激活(current) / 完成(done，可点回跳)；可访问角色 `list` + 每段 `listitem` + `aria-current="step"`（喂 L6.1/L6.4）。
- **Field**：`label`（关联 `for`/`id`）+ 输入控件 + `validator`（inline 错误文案，`aria-describedby`/`aria-invalid`）；错误态、聚焦态、禁用态（喂 L6.2/L6.4）。
  - 文本类：公司名称、姓名、邮箱、手机、卡号、有效期、CVV、开户行、对公账号。
  - 选择类：行业（select）、规模（select）、支付方式（RadioGroup）。
- **RadioGroup**（支付方式）：`radiogroup` + 两个 `radio`；change 事件驱动下方字段组显隐（互斥），喂 L6.3 联动。
- **Button**：primary = Next / Submit，secondary = Back；disabled（校验未过 / submitting）、loading（提交中防双击），喂 L6.5。
- **Inline validator**：必填非空 + 格式（邮箱、手机 11 位、卡号位数、CVV 3 位、有效期 MM/YY、对公账号数字）；错误就近显示，聚焦首个错误字段。

## 字段联动设计（L6.3 核心）
- step3 RadioGroup 值 = `card` → 显示 卡号 / 有效期 / CVV，隐藏 开户行 / 对公账号。
- 值 = `bank_transfer` → 反之。
- 切换即显隐（CSS + 受控值），公共字段（如有）不受影响；切换不清空本组外数据。

## Risks
- 联动字段组切换易丢可访问名：显隐组内的 Field 必须随显隐同步 `aria-hidden`/`disabled`，避免隐藏字段进 a11y 树（L6.4）。
- 校验时机：blur + 提交时全量校验，next 仅校验本步（避免提前报错打扰）。
- Back 保留数据：状态在向导层持有，Back/Next 不重置（L6.6）。
- 中文 CJK：label/占位/错误全中文；字体栈走 SwarSight 中文栈（craft 阶段确认 token）。
- 提交防双击：submitting 态全局禁用按钮 + 遮罩（L6.5）。

Ready for preview*（结构语义 floor：可读场景 + 命名 template 区域 + 关键 component 角色占位）。

## Preview 轮次记录

- **round-1（revise）**：人审选「需要修改」，feedback = `安师大安师大是`（无 anchor），`floor_pass=true / confirmed=false`。该 feedback 属 ADR-0008 语义垃圾串——结构 floor 放行（非空 feedback 触发），但零可执行改动信号；语义判定属 ui-evaluator（G6），非 floor。log.md 已记。无可派生改动 → round-2 仅按 decision report 自洽收紧结构（step3 联动不再折进 step1 卡，独立为步骤区域），不臆造迎合性改动。
- **round-2（revise，新证据）**：见 `preview/round-2.html`。人审选「需要修改」+ 真实 anchor `[select #s] 需要修改字体`，`floor_pass=true / confirmed=false`。这是具体可执行反馈（区别 round-1 的语义垃圾），不触发"两轮无新证据 stop"。font 属 craft 范畴（CJK type / 层级），但 prototype 层先修可执行项：`<select>/<option>` 不继承 CJK 栈是真实浏览器行为 → round-3 显式继承。
- **round-3（revise，新证据）**：见 `preview/round-3.html`，修复 #s 字体。人审再给 anchor `[#c] 改为一行两个`，`floor_pass=true / confirmed=false`。布局密度属 ui-picker/craft 表现层，但 prototype 层先执行：#c（公司名称）从独占行改为两列行。
- **round-4（再呈现，收敛提示）**：见 `preview/round-4.html`，step1 改两列行（公司名称 | 所属行业；公司规模次行）。结构已三次收敛，summary 提示可确认进 fill；字族/间距最终归 craft-guard。
- **round-4 CONFIRM ✅**：`confirmed=true / floor_pass=true`，confirm-round-4.json 落盘，report_ref 指向本 report → G5 满足。确认时人审另附 2 条 carry-forward 打磨 anchor（已确认但记录待 fill/craft 落实）：
  1. `[div 下一步] 修改按钮位置`（step1 actions 按钮布局）→ fill：actions 区右对齐、按钮间距统一。
  2. `[label 手机 *] label 需要与输入框在同一行`（step2 手机 label）→ fill：step2 label 改 inline 同行布局（而非块级独占）。

preview* 闭环：4 轮 HITL（round-1 ADR-0008 语义垃圾 revise → round-2 字体 anchor revise → round-3 布局 anchor revise → round-4 confirm），真实 confirm json 产出。进 Fill。
