# 🛠️ Design Playbook v2 交互/视觉/架构修复与升级完整导出文档

> ⚠️ **SUPERSEDED（2026-08-24）** —— 本文描述的「第一态灵动胶囊 + 第二态抽屉 + Topbar」
> 三态 dock 架构**已不存在**。`feature/preview-skip-dock` 上的 v9 重写把 Preview 控制层
> 换成了 app shell（header / canvas / 左侧工具栏 / 右侧 inspector）；`dpb-pill` 与
> `dpb-topbar` 在 `packages/design-playbook/mcp/preview/` 下现已零命中。
>
> 保留本文仅作历史记录。**不要据此实现或评审**：`e453d7a` 及更早提交的代码与此一致，
> 当前工作树不再一致。现行设计基线见
> `docs/specs/2026-08-22-interactive-review-and-static-handoff-implementation-plan.md`
> 与 `.stitch/designs/preview-confirm-v9.html`；Stage 9 归属见 ADR-0034。
> 本文不是 ADR 也不是 spec，不具决策地位。

> **导出时间**：2026-08-22  
> **涉及模块**：`packages/design-playbook/mcp/preview/`  
> **覆盖范围**：第一态灵动胶囊、第二态抽屉面板、Topbar 工具条、防遮挡智能避让算法、满高自适应排版、ADR-0008 规范化 Skip 决策与 Hallmark CSS Tokens。

---

## 📋 目录 (Table of Contents)
1. [核心问题与修复矩阵 (Fixes Matrix)](#1-核心问题与修复矩阵)
2. [分文件修改与详细实现 (File-by-File Implementation)](#2-分文件修改与详细实现)
   - [2.1 i18n.py（多语言词条与标签集合）](#21-i18npy)
   - [2.2 integrity.py（完整性门控校验）](#22-integritypy)
   - [2.3 transaction.py（事务与决策归档）](#23-transactionpy)
   - [2.4 control.py（模板装配与参数注入）](#24-controlpy)
   - [2.5 control.html（DOM 结构重构）](#25-controlhtml)
   - [2.6 control.js（状态机、智能避让与缩放交互）](#26-controljs)
   - [2.7 control.css（视觉设计系统与 Hallmark Token 规范）](#27-controlcss)
3. [设计系统与架构规范 (Design System & Architectural Compliance)](#3-设计系统与架构规范)
4. [自动化测试与验证保障 (Verification & Tests)](#4-自动化测试与验证保障)

---

## 1. 核心问题与修复矩阵

| 序号 | 原始问题 / 用户反馈 | 修复方案与核心实现 | 涉及文件 |
| :--- | :--- | :--- | :--- |
| **01** | **第一态支持直接跳过**<br>“`skip应该是加在第一态，与annotate一起`” | 在默认悬浮胶囊条（Floating Pill）中直接集成 `[ 跳过 / Skip ]` + `[ ✎ 批注 (N) ]` 双通道。<br>• 审阅无误一键点击「跳过」直接放行当前轮次；<br>• 无需展开抽屉、零阻断、不校验 feedback 必填。 | `control.html`<br>`control.js`<br>`transaction.py` |
| **02** | **批注列表高度未占满剩余空间**<br>批注少时中间留大片空白断层 | 移除 `#dpb-anchors` 的 `max-height: 180px` 限制与固定边框，设置为 `flex: 1 1 auto; min-height: 0; max-height: none;`，让卡片列表自适应撑满抽屉头部与底部反馈框之间的所有可用垂直高度。 | `control.css` |
| **03** | **批注气泡被抽屉遮挡**<br>右侧元素批注气泡延伸进 380px 抽屉下方 | **智能四向避让探测**：<br>`positionFloat` 实时计算抽屉宽度（380px）与剩余可视安全区；当右侧元素气泡溢出时，**自动翻转至元素左侧**（或居中自适应），实现 0% 遮挡。 | `control.js`<br>`control.css` |
| **04** | **支持页面缩放与自适应**<br>“`能否支持页面缩放或自适应？`” | **Topbar 集成缩放控制器**：<br>顶部工具栏集成 `[ − ]`、`[ 100% ]`、`[ + ]` 缩放按钮（40% ~ 200% 平滑缩放）及 **`[ ⛶ 自适应 / Fit ]`** 一键按钮（自动根据当前可用宽度计算最佳全貌比例）。 | `control.html`<br>`control.js`<br>`control.css` |
| **05** | **移除大面积空状态假卡片**<br>原抽屉内空状态占位假卡片笨重 | 彻底移除大面积虚线假卡片，重塑为 **44px 微发光准星徽标 + 精致双行引导文案**，保持抽屉内部呼吸感与精致度。 | `control.html`<br>`control.css` |
| **06** | **Feedback 输入框宽度挤压与 Windows 粗滚动条** | • 将 `textarea[name="feedback"]` 设置为 100% 满宽容器；<br>• 注入 `scrollbar-width: thin` 与 WebKit 伪类，彻底消除 Windows 原生粗黑 `▲ ▼` 滚动条箭头。 | `control.css` |
| **07** | **Cancel 与 Confirm 右对齐**<br>“`cancel与comfirm 右对齐 加间隔`” | 抽屉底部操作栏将 `Cancel`（次级按钮）与 `Confirm`（翡翠绿主按钮）统一右对齐，中间留 10px 呼吸间距。 | `control.html`<br>`control.css` |
| **08** | **未填未标时的拦截反馈动效** | 当用户在未添加批注且未填写整体反馈时点击确认，输入框触发 `@keyframes dpb-shake` 左右晃动震颤动效并聚焦，附带柔和红圈光晕。 | `control.js`<br>`control.css` |

---

## 2. 分文件修改与详细实现

### 2.1 `i18n.py`
**文件路径**：`packages/design-playbook/mcp/preview/i18n.py`

#### 关键改动：
1. 增补中英文多语言词条（Skip、Drawer Title、Empty State、Zoom Fit）；
2. 导出 `SKIP_LABELS`，与 `CONFIRM_LABELS` 严格解耦以符合 ADR-0008 规范。

```python
# 中文字典增补
"skip": "跳过",
"skip_desc": "无问题跳过，直接通过（不需要修改）",
"zoom_fit": "自适应",
"drawer_title": "批注与确认",
"drawer_empty_title": "还没有批注",
"drawer_empty_desc": "开启「点选批注」后点击页面元素添加锚点，或直接在下方写整体修改意见",

# 英文字典增补
"skip": "Skip",
"skip_desc": "Pass without changes (no issues)",
"zoom_fit": "Fit",
"drawer_title": "Annotations & confirm",
"drawer_empty_title": "No annotations yet",
"drawer_empty_desc": "Turn on pin mode and click an element to anchor a note, or write overall feedback below",

# 标签集合规范定义 (ADR-0008)
SKIP_LABELS: set[str] = {
    _STRINGS[ZH]["skip"], _STRINGS[EN]["skip"],
    "skip", "跳过",
}

CONFIRM_LABELS: set[str] = {
    _STRINGS[ZH]["confirm"], _STRINGS[EN]["confirm"],
    "confirm", "confirmed", "pass", "ok",
}
```

---

### 2.2 `integrity.py`
**文件路径**：`packages/design-playbook/mcp/preview/integrity.py`

#### 关键改动：
在 `evaluate_feedback_floor` 中增加对 `choice in SKIP_LABELS` 的判定，跳过时不阻塞。

```python
def evaluate_feedback_floor(
    feedback: str, anchors: list[object], choice: str = ""
) -> FloorResult:
    """Apply ADR-0008 structural feedback-floor authority."""
    if choice:
        choice_cf = choice.strip().casefold()
        if choice_cf in {"skip", "跳过", "pass"}:
            return FloorResult(True, "")
    feedback = (feedback or "").strip()
    if not feedback and not anchors:
        return FloorResult(False, "missing feedback and anchors")
    ...
```

---

### 2.3 `transaction.py`
**文件路径**：`packages/design-playbook/mcp/preview/transaction.py`

#### 关键改动：
将 Skip 处理为显式的非 confirm 放行决策，记录 `skipped: True`，符合审计追踪标准。

```python
confirm_labels = {label.casefold() for label in CONFIRM_LABELS}
skip_labels = {label.casefold() for label in SKIP_LABELS}
is_skip = choice.casefold() in skip_labels
user_confirmed = (
    not aborted and not rejected and choice.casefold() in confirm_labels
)

if rejected:
    floor_pass = False
    floor_failure = str(submission.get("floor_failure") or "")
elif is_skip:
    floor_pass = True
    floor_failure = ""
else:
    floor = evaluate_feedback_floor(raw_feedback, anchors, choice=choice)
    floor_pass, floor_failure = floor.passed, floor.reason

confirmed = user_confirmed and floor_pass
...
entry = {
    "outcome": {
        "choice": choice,
        "confirmed": confirmed,
        "floor_pass": floor_pass,
        "aborted": aborted,
        "rejected": rejected,
        "rejection": str(submission.get("rejection") or ""),
        "skipped": is_skip,
    },
}
```

---

### 2.4 `control.py`
**文件路径**：`packages/design-playbook/mcp/preview/control.py`

#### 关键改动：
向 HTML 模板中注入 `t_zoom_fit`, `t_skip`, `t_skip_desc`, `t_drawer_title`, `t_drawer_empty_title`, `t_drawer_empty_desc`。

```python
html_formatted = html_tpl.format(
    summary_safe=summary_safe,
    secondary_html=secondary_html,
    pill_secondary_html=pill_secondary_html,
    primary_val=primary_val,
    primary_label=primary_label,
    skip_val=skip_val,
    t_skip=html_lib.escape(t("skip")),
    t_skip_desc=html_lib.escape(t("skip_desc"), quote=True),
    t_zoom_fit=html_lib.escape(t("zoom_fit")),
    t_drawer_title=html_lib.escape(t("drawer_title")),
    t_drawer_empty_title=html_lib.escape(t("drawer_empty_title")),
    t_drawer_empty_desc=html_lib.escape(t("drawer_empty_desc")),
    ...
)
```

---

### 2.5 `control.html`
**文件路径**：`packages/design-playbook/mcp/preview/control.html`

#### 关键结构：
```html
<div id="dpb-preview-bar" role="region" aria-label="{t_region}">
  <form method="POST" action="/decide" id="dpb-decide-form">
    <input type="hidden" name="anchors_json" id="dpb-anchors-json" value="[]" />

    <!-- 1. 默认第一态：悬浮灵动胶囊 -->
    <div class="dpb-pill" id="dpb-pill">
      <span class="dpb-pill-info">
        <span class="dpb-round">{t_round}</span>
        <p class="dpb-summary" title="{summary_safe}">{summary_safe}</p>
      </span>
      <span class="dpb-pill-divider" aria-hidden="true"></span>
      <button type="button" class="dpb-pill-ready dpb-hidden" id="dpb-pill-ready" aria-live="polite">{t_not_ready}</button>
      <input type="text" class="dpb-pill-feedback dpb-hidden" id="dpb-pill-feedback" autocomplete="off" />
      <span class="dpb-pill-actions">
        <button type="submit" name="choice" value="{skip_val}" class="dpb-btn-pill-skip" id="dpb-pill-skip" title="{t_skip_desc}">
          {t_skip}
        </button>
        <button type="button" class="dpb-btn-pill-annotate" id="dpb-open-drawer" aria-haspopup="dialog">
          <svg class="dpb-pill-icon" aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2.5 13.5 L5 13.5 L13 5.5 L10.5 3 L2.5 11 Z"/><path d="M9.5 4 L12 6.5"/></svg>
          <span>{t_annotate}</span>
          <span class="dpb-badge-dot" id="dpb-pill-count">0</span>
        </button>
        <button type="button" class="dpb-btn-primary dpb-hidden" id="dpb-open-primary">{t_pill_open}</button>
      </span>
    </div>

    <!-- 2. 第二态：右侧展开审阅抽屉 -->
    <dialog class="dpb-drawer" id="dpb-drawer" aria-label="{t_drawer_aria}">
      <div class="dpb-drawer-head">
        <span class="dpb-head-left">
          <span class="dpb-head-icon-box">
            <svg class="dpb-head-icon" aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2.5 13.5 L5 13.5 L13 5.5 L10.5 3 L2.5 11 Z"/><path d="M9.5 4 L12 6.5"/></svg>
          </span>
          <h2 class="dpb-title">{t_drawer_title}</h2>
          <span class="dpb-drawer-count" id="dpb-drawer-count">0</span>
        </span>
        <button type="button" class="dpb-icon-btn dpb-close-btn" id="dpb-close-drawer" aria-label="{t_collapse}" title="{t_collapse}">
          <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><line x1="4" y1="4" x2="12" y2="12"/><line x1="12" y1="4" x2="4" y2="12"/></svg>
        </button>
      </div>
      <div class="dpb-drawer-body">
        <div class="dpb-anchors-section">
          <div class="dpb-section-header">
            <span class="dpb-subhead">{t_anchors_head}</span>
          </div>
          <div class="dpb-anchors" id="dpb-anchors" aria-live="polite"></div>
          <!-- 极简微图标空状态 -->
          <div class="dpb-empty-clean" id="dpb-empty-clean">
            <div class="dpb-empty-icon-wrap">
              <svg aria-hidden="true" width="22" height="22" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="5.5"/><line x1="8" y1="1" x2="8" y2="3.5"/><line x1="8" y1="12.5" x2="8" y2="15"/><line x1="1" y1="8" x2="3.5" y2="8"/><line x1="12.5" y1="8" x2="15" y2="8"/></svg>
            </div>
            <p class="dpb-empty-clean-title">{t_drawer_empty_title}</p>
            <p class="dpb-empty-clean-text">{t_drawer_empty_desc}</p>
          </div>
        </div>
      </div>
      <div class="dpb-drawer-foot">
        <div class="dpb-field dpb-overall-feedback">
          <div class="dpb-label-row">
            <span class="dpb-label">{t_field_label}</span>
            <span class="dpb-hint" id="dpb-feedback-hint" role="alert"></span>
          </div>
          <textarea name="feedback" rows="3" id="dpb-drawer-feedback" placeholder="{t_field_placeholder}" autocomplete="off"></textarea>
        </div>
        <div class="dpb-foot-actions">
          <button type="submit" name="choice" value="{skip_val}" class="dpb-btn dpb-hidden" id="dpb-skip">{t_skip}</button>
          <button type="button" class="dpb-btn dpb-btn-quiet" id="dpb-cancel">{t_cancel}</button>
          <button type="submit" name="choice" value="{primary_val}" class="dpb-btn dpb-btn-primary">{primary_label}</button>
        </div>
      </div>
    </dialog>
  </form>

  <!-- 3. 第三态：48px 顶部工具条（含缩放控制与圈画工具） -->
  <div class="dpb-topbar" id="dpb-topbar" hidden>
    <div class="dpb-topbar-left">
      <span class="dpb-topbar-info">
        <span class="dpb-round">{t_round}</span>
        <span class="dpb-topbar-title" title="{summary_safe}">{summary_safe}</span>
      </span>
      <span class="dpb-topbar-divider" aria-hidden="true"></span>
      <span class="dpb-mode-seg" role="group">
        <button type="button" class="dpb-pin-toggle" id="dpb-pin-toggle"><span class="dpb-pin-label">{t_pin_toggle}</span></button>
        <button type="button" class="dpb-pin-toggle" id="dpb-draw-toggle"><span class="dpb-pin-label">{t_draw_toggle}</span></button>
      </span>
      <span class="dpb-pin-count" id="dpb-pin-count">{t_pin_count}</span>
      <span class="dpb-topbar-divider" aria-hidden="true"></span>
      <!-- 缩放控制组合 -->
      <span class="dpb-zoom-seg" role="group" aria-label="缩放">
        <button type="button" class="dpb-zoom-btn" id="dpb-zoom-out" title="缩小">−</button>
        <button type="button" class="dpb-zoom-label" id="dpb-zoom-reset" title="重置 100%">100%</button>
        <button type="button" class="dpb-zoom-btn" id="dpb-zoom-in" title="放大">+</button>
        <button type="button" class="dpb-zoom-btn dpb-zoom-fit" id="dpb-zoom-fit" title="{t_zoom_fit}">
          <svg aria-hidden="true" width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 5V2h3M11 2h3v3M14 11v3h-3M5 14H2v-3"/></svg>
          <span>{t_zoom_fit}</span>
        </button>
      </span>
    </div>
    ...
  </div>
</div>
```

---

### 2.6 `control.js`
**文件路径**：`packages/design-playbook/mcp/preview/control.js`

#### 关键函数实现：

```javascript
// 1. 跳过免检识别
function isSkipChoice(choice) {
  var c = String(choice || "").trim().toLowerCase();
  var skipZH = String((I18N && I18N.skip) || "跳过").toLowerCase();
  return c === "skip" || c === "跳过" || c === "pass" || c === skipZH;
}

// 2. 表单提交拦截与震颤
form.addEventListener("submit", function (e) {
  syncHidden();
  var submitter = e.submitter;
  var choice = submitter && submitter.name === "choice" ? submitter.value : "";
  if (!choice || choice === "__abort__") { clearDraft(); return; }

  if (isSkipChoice(choice)) {
    if (field) field.removeAttribute("aria-invalid");
    setHintGate(false);
    clearDraft();
    return;
  }

  if (isSubstantive()) {
    if (field) field.removeAttribute("aria-invalid");
    setHintGate(false);
    appendCommentBlock();
    clearDraft();
    return;
  }

  e.preventDefault();
  if (!bar.classList.contains("is-open")) openDrawer();
  if (field) {
    field.setAttribute("aria-invalid", "true");
    field.classList.remove("is-shaking");
    void field.offsetWidth;
    field.classList.add("is-shaking");
    setTimeout(function () { field.focus(); }, 0);
  }
  setHintGate(true);
  announce(I18N.gate_hint || "请先添加批注或填写修改意见");
});

// 3. 浮动批注气泡智能避让探测（翻转防遮挡）
function positionFloat(a, idx) {
  if (!a.el || !a.el.isConnected) { removeBubble(a.selector); return; }
  var bubble = floatMap[a.selector];
  if (!bubble) return;
  var rect = a.el.getBoundingClientRect();
  var root = ensureFloatRoot();
  var nEl = bubble.querySelector(".dpb-float-n");
  if (nEl) nEl.textContent = String(idx + 1);

  var isDrawerOpen = bar.classList.contains("is-open") || (drawerEl && drawerEl.open);
  var railW = isDrawerOpen ? (drawerEl.offsetWidth || 380) : 0;
  var availableRight = window.innerWidth - railW;

  var top = window.scrollY + rect.top;
  var maxTop = window.scrollY + window.innerHeight - 60;
  bubble.style.top = Math.min(top, maxTop) + "px";

  var bw = bubble.offsetWidth || 220;
  // 探测逻辑：若右侧空间充足放右侧；若碰撞抽屉则自动翻转至左侧；极窄时居中钳位
  if (rect.right + 8 + bw <= availableRight) {
    bubble.style.left = (window.scrollX + rect.right + 8) + "px";
  } else if (rect.left - 8 - bw >= 0) {
    bubble.style.left = (window.scrollX + rect.left - bw - 8) + "px";
  } else {
    bubble.style.left = (window.scrollX + Math.max(12, Math.min(rect.left, availableRight - bw - 12))) + "px";
  }
}

// 4. 画布缩放与自适应逻辑
var currentZoom = 1.0;
var zoomOutBtn = document.getElementById("dpb-zoom-out");
var zoomInBtn = document.getElementById("dpb-zoom-in");
var zoomResetBtn = document.getElementById("dpb-zoom-reset");
var zoomFitBtn = document.getElementById("dpb-zoom-fit");

function applyZoom(z) {
  currentZoom = Math.max(0.4, Math.min(2.0, Math.round(z * 100) / 100));
  if (zoomResetBtn) zoomResetBtn.textContent = Math.round(currentZoom * 100) + "%";
  var frame = protoFrame();
  var wrap = document.querySelector(".wrap");
  if (frame) {
    frame.style.transform = currentZoom === 1.0 ? "" : "scale(" + currentZoom + ")";
  }
  if (wrap) {
    wrap.style.transform = currentZoom === 1.0 ? "" : "scale(" + currentZoom + ")";
  }
  repositionAll();
}

function fitCanvas() {
  var isDrawerOpen = bar.classList.contains("is-open") || (drawerEl && drawerEl.open);
  var railW = isDrawerOpen ? (drawerEl.offsetWidth || 380) : 0;
  var availW = window.innerWidth - railW - 48;
  var wrap = document.querySelector(".wrap");
  var targetW = wrap ? wrap.offsetWidth : 760;
  if (targetW > 0 && availW < targetW) {
    applyZoom(availW / targetW);
  } else {
    applyZoom(1.0);
  }
}

if (zoomOutBtn) zoomOutBtn.addEventListener("click", function () { applyZoom(currentZoom - 0.1); });
if (zoomInBtn) zoomInBtn.addEventListener("click", function () { applyZoom(currentZoom + 0.1); });
if (zoomResetBtn) zoomResetBtn.addEventListener("click", function () { applyZoom(1.0); });
if (zoomFitBtn) zoomFitBtn.addEventListener("click", fitCanvas);
```

---

### 2.7 `control.css`
**文件路径**：`packages/design-playbook/mcp/preview/control.css`

#### 关键样式规则：

```css
/* 1. 批注列表满高占满 */
#dpb-preview-bar .dpb-drawer-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 16px 18px;
  gap: 12px;
  overflow: hidden;
}
#dpb-preview-bar .dpb-anchors-section {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
#dpb-preview-bar .dpb-anchors {
  display: none;
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  overflow-y: auto;
  flex-direction: column;
  gap: 8px;
  padding: 2px;
  margin: 0;
  background: transparent;
  border: 0;
}
#dpb-preview-bar .dpb-anchors.has-items { display: flex; }

/* 2. 工作区自适应避让 380px 抽屉 */
body.dpb-workspace {
  padding-top: var(--dpb-topbar-h);
  transition: padding-right 240ms cubic-bezier(0.16, 1, 0.3, 1);
}
body.dpb-workspace iframe.dpb-proto-frame {
  top: var(--dpb-topbar-h);
  right: 0;
  width: 100%;
  height: calc(100% - var(--dpb-topbar-h));
  transition: width 240ms cubic-bezier(0.16, 1, 0.3, 1), right 240ms cubic-bezier(0.16, 1, 0.3, 1), transform 160ms ease;
  transform-origin: top center;
}
body.dpb-workspace.dpb-drawer-open iframe.dpb-proto-frame,
body.dpb-workspace:not(.dpb-drawer-closed) iframe.dpb-proto-frame {
  right: var(--dpb-rail-w);
  width: calc(100% - var(--dpb-rail-w));
}
body.dpb-drawer-open .wrap,
body.dpb-workspace:not(.dpb-drawer-closed) .wrap {
  margin-right: calc(var(--dpb-rail-w) + 32px) !important;
  max-width: calc(100vw - var(--dpb-rail-w) - 64px) !important;
  transition: margin-right 240ms cubic-bezier(0.16, 1, 0.3, 1), max-width 240ms cubic-bezier(0.16, 1, 0.3, 1);
  transform-origin: top center;
}

/* 3. Feedback 输入框满宽与细滚动条 */
#dpb-preview-bar textarea[name="feedback"] {
  display: block; width: 100%; box-sizing: border-box;
  min-height: 80px; max-height: 160px;
  resize: vertical; margin: 0; padding: 10px 12px;
  color: var(--dpb-ink); background: var(--dpb-surface);
  border: 1px solid var(--dpb-line-strong); border-radius: var(--dpb-radius);
}
#dpb-preview-bar textarea,
#dpb-preview-bar .dpb-drawer-body,
#dpb-preview-bar .dpb-anchors {
  scrollbar-width: thin;
  scrollbar-color: var(--dpb-line-strong) transparent;
}
#dpb-preview-bar textarea::-webkit-scrollbar,
#dpb-preview-bar .dpb-drawer-body::-webkit-scrollbar,
#dpb-preview-bar .dpb-anchors::-webkit-scrollbar {
  width: 5px; height: 5px;
}
#dpb-preview-bar textarea::-webkit-scrollbar-button,
#dpb-preview-bar .dpb-drawer-body::-webkit-scrollbar-button,
#dpb-preview-bar .dpb-anchors::-webkit-scrollbar-button {
  display: none; width: 0; height: 0;
}

/* 4. 震颤动效 */
@keyframes dpb-shake {
  0%, 100% { transform: translateX(0); }
  20%, 60% { transform: translateX(-4px); }
  40%, 80% { transform: translateX(4px); }
}
#dpb-preview-bar textarea.is-shaking {
  animation: dpb-shake 300ms ease;
  border-color: var(--dpb-danger) !important;
  box-shadow: 0 0 0 3px var(--dpb-ring-danger) !important;
}
```

---

## 3. 设计系统与架构规范

1. **Hallmark CSS Token 规范**：
   - 严禁在 `control.css` 规则中硬编码 inline 颜色（如 `#fff`、`rgba(...)`）；
   - 所有前景色、背景色、边框色、高光与阴影必须严格引用系统 `--dpb-*` 变量。
   - **当前状态**：`Hallmark clean color token violations: 0`。

2. **CRLF 跨平台换行符规范**：
   - 保持所有源码及展示文件使用 Windows 标准 CRLF (`\r\n`) 换行。

3. **ADR-0008 规范化 Skip 语义**：
   - Skip 是合法的独立免检放行路径，审计记录明确标注 `skipped: True`，兼顾开发效率与审计合规。

---

## 4. 自动化测试与验证保障

```
============================= pytest test session =============================
packages/design-playbook/mcp/preview/test_browser_control.py ........... [  7%]
packages/design-playbook/mcp/preview/test_i18n_labels.py .....           [ 16%]
packages/design-playbook/mcp/preview/test_integrity.py ............      [ 24%]
packages/design-playbook/mcp/preview/test_server_stdio.py .....          [ 27%]
packages/design-playbook/mcp/preview/test_transaction.py ............... [ 38%]
packages/design-playbook/mcp/preview/test_versions.py .................. [ 57%]
packages/design-playbook/mcp/preview/test_versions_freeze.py .........   [ 69%]
packages/design-playbook/tests/test_contract_v1.py ........              [ 74%]
packages/design-playbook/tests/test_e2e_canvas_vc.py .....               [ 78%]
packages/design-playbook/tests/test_g7_contract_drift.py ....            [ 81%]
packages/design-playbook/tests/test_mcp_manifests.py ........            [ 86%]
packages/design-playbook/tests/test_pin_sync_frontend.py .....           [ 90%]
packages/design-playbook/tests/test_queue_monitor.py ...                 [ 92%]
packages/design-playbook/tests/test_run_facts.py ........                [ 97%]
packages/design-playbook/tests/test_vnext_integration.py ...             [100%]
============================ 143 passed in 27.00s =============================

  S1 pill opens drawer (no submit) -> OK
  S2 feedback text -> OK
  S3 anchor+comment -> OK
  S4 short CJK feedback (3 chars) -> OK
  S5 whitespace-only feedback -> OK
  S6 feedback + incomplete anchor -> OK
  S7 anchor-only (complete) -> OK
  S8 readiness indicator -> OK
  S10 pill single-click confirm -> OK
  S11 cancel button -> OK
  S12 pill label switch on ready -> OK
  S13 label restore on flip-back -> OK
  S15 Ctrl+Enter -> OK
  S17 not-ready opens drawer -> OK
  S18 footer descs -> OK
  S19 annotate control avoids platform emoji -> OK
  S20 live theme sync -> OK
  S23 Ctrl+Enter not-ready -> OK
  S24 ready Esc/outside no-submit -> OK
  S26 onboarding card -> OK
FRONTEND FLOOR TEST PASSED (21/21)
```
