# 版本控制数据模型 — VC data model（05 票资产）

> Ticket 05 资产：为"事件溯源 + 命名快照叠加（round 级）"设计数据模型与 API 形状。
> 输入：03 资产（事件溯源 §5 + 快照列表式 §3）、01 资产 §3/§4、`transaction.py` 全文。
> 状态：**设计草案，不实现**。粒度 round 级（非操作级），G5 不变量零冲突，向后兼容 v0.10 产物。

---

## 0. 设计原则（从 03 继承）

1. **append-only 权威 + 可重建投影分离**（ADR-0013 模式）：决策/命名是权威文件（原子写、不可变、不可覆盖）；log/索引是投影（可从权威重建）。
2. **round 是事件**：现有 `decision-round-N.json` 已经是事件（append-only、不可变、有序）。事件溯源**不建新存储**，而是把现有 entry 链当作事件流，补两个能力：replay（`state_at(N)`）+ fork。
3. **命名版本是元事件**：命名发生在决策之后，是"对事件流的事件"（用户输入），不是决策 entry 的一部分——独立权威文件，不塞进不可变 entry。
4. **fork 不破坏单线程 G5**：fork = 新 preview 目录内的独立线性链，携带来源元数据。每个目录内 round 仍线性递增，"use next round" 语义不变。
5. **向后兼容**：entry schema 保持 v1；新增字段全部可选；新增文件不影响旧读侧（validate_run 只扫 decision/confirm/log）。

---

## 1. 现状盘点（角色划分）

| 文件 | 角色 | 权威/投影 | 来源 |
| --- | --- | --- | --- |
| `decision-round-N.json` | 决策事件（每 round 一个，append-only） | **权威** | transaction.py:593-611 |
| `confirm-round-N.json` | 确认投影（user_confirmed 时） | 投影 | transaction.py:418-448 |
| `log.md` | 审计投影（从全部 entries 重建） | 投影 | transaction.py:374-406 |
| `round-N.html` | 原型快照（html 模式自动写） | 权威（内容即快照） | transaction.py:36-48 |
| `decision-round-N.lock` | 单轮锁（O_EXCL + heartbeat + stale recovery） | 瞬时 | transaction.py:190-251 |

**关键结论**：事件溯源的数据底座已存在。缺的是：① 命名版本（元事件）权威文件；② replay/fork API；③ 时间线浏览的统一视图。

---

## 2. 事件溯源层设计（新文件：无——复用现有 entry 链）

### 2.1 entry 即事件

现有 `decision-round-N.json` 直接充当事件。无需新事件文件。事件类型在语义上从 `outcome` 派生：

| 语义事件 | 判定 | 现有字段 |
| --- | --- | --- |
| `round_confirmed` | `outcome.user_confirmed and outcome.floor_pass` | transaction.py:584 |
| `round_revised` | 非 abort 且非 confirmed（`choice` 是 revise 类） | transaction.py:572-578 |
| `round_aborted` | `outcome.aborted` | transaction.py:571 |
| `round_rejected` | `outcome.rejected` | transaction.py:570 |

### 2.2 `state_at(N)` — replay API

**语义**：回到 round N 的确认后状态（原型 + 决策 + 该时刻前的命名版本）。**只读，不改变任何文件**（非破坏性）。

```python
def state_at(preview_dir: Path, round_n: int) -> dict[str, Any]:
    """Return the replayable state at round N. Raises NotFound if N has no entry."""
    entry = _load_entry(preview_dir / f"decision-round-{round_n}.json")   # 复用现有
    prototype = _prototype_at(preview_dir, entry)                          # 见下
    confirm = _load_confirm(preview_dir, round_n)                          # 复用现有读侧
    versions = [v for v in _valid_versions(preview_dir) if v["round"] <= round_n]
    return {
        "round": round_n,
        "prototype_html": prototype["html"],        # html 模式：round-N.html 内容
        "prototype_path": prototype["path"],        # path 模式：外部文件路径（html=None）
        "binding": entry["binding"],
        "outcome": entry["outcome"],
        "confirm": confirm,                          # None 若该轮未确认
        "versions": versions,                        # 时间线视图在 round N 的截断
        "digest": entry["binding"]["digest"],
    }
```

**语义边界**：
- N 无 entry → 明确错误（`PreviewTransactionError` 风格，retryable=False），不是静默回退。
- N 是 aborted/rejected round → 返回该状态但标注 `outcome.aborted/rejected`（供 UI 区分）。
- path 模式（原型是外部文件）：`prototype_html=None`，返回 `prototype_path`；不读外部文件内容（避免大文件）。
- 跨 round 冲突不适用：replay 是读操作，与"use next round" 写路径无交集。

### 2.3 `fork(...)` — 派生替代方案

**语义**：从 round N 派生一条独立链（备选方案对比，Figma 分支的本地替身）。**新 preview 目录**，G5 单线程不变量零冲突。

```python
def fork(
    source_dir: Path, *, branch: str, from_round: int,
    new_dir: Path, report_ref: str, summary: str,
) -> dict[str, Any]:
    """Derive a new linear chain from round N of source_dir. Returns fork record."""
    src = state_at(source_dir, from_round)
    new_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 1,
        "branch": branch,
        "forked_from_round": from_round,
        "forked_from_digest": src["digest"],
        "forked_from_decision_id": src["outcome"],   # 见下——只存 decision_id
        "forked_from_dir": str(source_dir),
        "timestamp": _now_iso(),
    }
    _atomic_write(new_dir / "fork.json", _json_text(record))
    # 原型：html 模式复制 round-N.html → new_dir/round-1.html（fork 目录 round 从 1 重计）
    if src["prototype_html"] is not None:
        (new_dir / "round-1.html").write_text(src["prototype_html"], encoding="utf-8")
    # 返回：调用方据此起新 preview_prototype（path=new_dir/round-1.html 或 html=内容）
    return {"fork": record, "start_prototype": str(new_dir / "round-1.html")}
```

**关键决策**：
- **fork 目录内 round 从 1 重新开始**：干净、避免 "use next round" 语义混乱；`fork.json` 记录来源（branch/forked_from_round/digest）。
- fork 不自动写 decision entry（那是 preview_prototype 新一轮的职责）；fork.json 是唯一的 fork 权威。
- 对比 UI（06 原型）读 `fork.json` + 两目录的 `state_at` 做并排。
- 目录命名约定：`preview/fork-<branch-slug>/`（html 模式）或调用方指定（path 模式）。

---

## 3. 命名快照层设计（新文件：`version-<seq>.json`）

### 3.1 权威文件 schema

每打一个命名版本 = 一个新文件（append-only、原子写），`seq` 从 1 递增：

```json
{
  "schema_version": 1,
  "seq": 3,
  "version_id": "v-1f9a...",
  "name": "确认版·桌面端",
  "kind": "confirmed",          // confirmed | revised | custom
  "round": 4,
  "decision_id": "d-...",
  "timestamp": "2026-08-07T02:00:00+08:00",
  "note": "可选备注"
}
```

### 3.2 约束

- **round 必须存在**：`version-<seq>.json` 写入前校验 `decision-round-{round}.json` 存在（`_load_entry` 非 None），否则拒绝。
- **name 非空**，≤ 80 字符；同一 round 可多次命名（kind 区分，如"确认版"+"修订版"）。
- **不可变**：命名一旦写入不可覆盖/删除；重命名 = 新 version 事件（append-only 语义）。
- **seq 分配**：原子读 `version-*.json` 最大 seq + 1（与 `_round_from_path` 同类扫描模式），单锁保护（复用 `_round_lock` 模式或轻量 `version-<seq>.lock`——命名低频，简单 O_EXCL 即可）。

### 3.3 时间线浏览数据源

统一视图 = **decision entries ∪ version entries**，按 `timestamp` 合并排序：

```python
def timeline(preview_dir: Path) -> list[dict[str, Any]]:
    """Merged, timestamp-ordered view: decision events + named versions."""
    decisions = _valid_entries(preview_dir)          # 现有（含投影到 log.md 的读侧）
    versions = _valid_versions(preview_dir)          # 新：扫 version-*.json
    return sorted(decisions + versions, key=lambda e: (e["timestamp"], e.get("seq", 0)))
```

投影更新：`log.md` 增加 `## versions` 段（从 `version-*.json` 重建——投影角色，权威是 version 文件本身）。`_commit_projections` 扩展：写 version 时同时重写 log.md。

---

## 4. API 汇总（签名级，实现归后续票）

| API | 位置 | 类型 | 签名 | 说明 |
| --- | --- | --- | --- | --- |
| `state_at` | versions.py | 读 | `(preview_dir, round_n) -> dict` | replay 到 round N |
| `fork` | versions.py | 写 | `(source_dir, *, branch, from_round, new_dir, report_ref, summary) -> dict` | 派生新链 |
| `create_named_version` | versions.py | 写 | `(preview_dir, *, round_n, name, kind, note) -> dict` | 打命名版本 |
| `timeline` | versions.py | 读 | `(preview_dir) -> list` | 时间线统一视图 |
| `list_versions` | versions.py | 读 | `(preview_dir) -> list` | 仅命名版本 |

复用：`_atomic_write` / `_json_text` / `_load_entry` / `_valid_entries` / `_round_lock`（import 复用，不改 transaction.py 现有逻辑）。新增独立模块 `mcp/preview/versions.py`，transaction.py 保持原样（最小侵入）。

---

## 5. 锚点 AST 化（anchor schema v2 — 局部）

**目标**：cssPath 跨轮失效问题（01 资产 §4"跨版本锚点一致性：无"）。**不做全文档 AST**（那是方向 B），只给锚点稳定身份 + 重连特征。

### 5.1 anchor schema v2（可选新字段，读侧兼容）

```json
{
  "selector": "div.card > h2",
  "label": "h2 \"标题\"",
  "comment": "太挤",
  "tag": "h2",
  "node_id": "a1f3",                    // 新增（可选）：round 内稳定身份
  "features": {                          // 新增（可选）：跨轮重连特征
    "tag": "h2",
    "text": "标题",
    "classes": ["card-title"],
    "aria_label": null
  }
}
```

- **node_id 生成**（服务端，提交时）：anchors 排序后 `sha256(round|index|selector)[:8]`——round 内稳定、跨轮不可比（轮变就变）。
- **跨轮重连**：不承诺自动（parent 无法读 sandboxed iframe DOM，01 资产 §5/§7）。最小语义 = 存 features，重连策略留给实现票（可选：用户手动重 pin 时用 features 预选候选）。
- **读侧兼容**：`validate_run` 只读 selector/comment/label/tag，新增字段被忽略。`_check_feedback_floor` 同样只看 selector/comment。

---

## 6. 与 transaction.py 的关系 + 向后兼容

| 变更 | 影响 | 兼容性 |
| --- | --- | --- |
| 新增 `versions.py` 模块 | 无现有改动；import 复用工具函数 | ✅ 纯新增 |
| `version-<seq>.json` 新文件 | 在 preview_dir；validate_run 不扫 | ✅ 纯新增 |
| anchor schema v2（+node_id/+features） | outcome.anchors 内可选字段 | ✅ 读侧忽略未知字段 |
| `log.md` 加 `## versions` 段 | 投影扩展 | ✅ 追加不破坏（旧 log 无此段仍合法） |
| `state_at`/`fork` | 新 API，不动现有调用链 | ✅ 纯新增 |
| **不改** entry schema（保持 v1） | — | ✅ |
| **不改** lock / round 递增 / "use next round" | — | ✅ G5 不变量零冲突 |

**风险点**：
- `version-*.json` 与 `decision-round-*.json` 的 glob 模式不冲突（不同前缀），`_valid_entries` 的 `decision-round-*.json` 模式不受影响。
- `fork` 目录内 round-1.html 与主目录 round-1.html 在**不同目录**，无文件冲突；若 fork 目录恰好是主目录的兄弟路径（`preview/fork-x/`），glob 也不跨子目录。

---

## 7. 落地拆票建议（05 resolve 后 graduate）

- **05a（实现，feature/canvas-thickening）**：`versions.py`（state_at / fork / create_named_version / timeline）+ log.md versions 段 + 测试（复用 `_atomic_write`/`_load_entry` 的测试模式）。
- **05b（实现）**：anchor schema v2（提交侧生成 node_id/features）+ 回归测试（validate_run 读侧兼容）。
- **06（原型，HITL）**：命名版本 + 时间线浏览 + replay/fork UX —— 现 unblocked，消费本资产的 schema/API 形状做 rough artifact。
- **发布**：随 v0.11.x minor（release transaction，ADR-0015）。

> 设计草案终止于此。schema/API 是否调整由 06 原型 UX 反馈 + 实现票裁决。