# Local-VC Interpretations —「本地版本控制」的 6 种形态

Ticket: `issues/03-local-vc-interpretations.md`（resolved 2026-08-07）
状态：research 资产，**不锁定选型**。锁定是后续 grilling ticket 的工作。
范围：只为 effort 提供"本地版本控制"的形态空间（6 种，落在 5–7 区间）。

---

## 0. 当前 round 机制的基线（判断契合度的锚）

先固化现状，后续所有"接入成本 / G5 兼容"都以此为参照（来源：`packages/design-playbook/mcp/preview/transaction.py` + `showcase/preview/` + `.scratch/design-playbook-v0/dogfood/2026-07-20-007-multi-step-form/preview/`）：

- `decision-round-{N}.json`：**不可变、append-only 的条目**——含 binding（round / prototype_html_hash / report_ref / summary / options 的 SHA-256）、timestamp、outcome（confirmed / floor_pass / anchors / feedback）。同 round 绑定不可覆盖（`TransactionConflict`）。
- `round-{N}.html`：inline HTML 时整页**不可变快照**，由 `_ensure_prototype` 写入 preview 目录。
- `confirm-round-{N}.json` + `log.md`：**投影**（`_commit_projections`），从 entries 重放生成人类可读 log。
- round 是严格递增正整数，per-round 锁（`_round_lock`）保证单线程权威。

→ 结论（先抛）：当前机制已是 **append-only 事件日志 + 快照 + 投影**的混合雏形。`decision-round-N.json` 就是事件，`log.md` 就是重放投影，`round-N.html` 就是快照。**它最接近"事件溯源"，其次"快照列表"。**

---

## 1. Git 式（snapshot + 三路合并引擎）

### 定义
以 git 的存储模型为代表：每次 commit 存一棵完整快照树（blob/tree/commit，内容寻址），分支是 commit 指针，合并用三路合并（base + ours + theirs）文本 diff。用户心智上版本 = commit 历史 + 分支图。jujutsu（jj）是它的现代变体：丢弃 staging area，**working copy 本身就是 commit**，每次跑 `jj` 命令自动快照，另有 operation log 使任意操作可 `jj undo`；仍以 git 对象作后端（`.jj/` 与 `.git/` 并存）。git-annex 则是把大文件指针化、内容移到外部存储的变体。

### 数据形态
`.git/`（或 `.jj/`）目录 + 工作树；对象为二进制（zlib 压缩）但内容寻址，`.git/objects` 不可直接读，须经 `git cat-file`；人类可读性来自工作树与 `git log`/`git diff` 的输出。每个 commit 是完整快照，git 用 delta 压缩省空间。

### 接入成本
高。要么直接集成 git（当前 effort 内仓库本已是 git repo，但 preview 产物是临时 HTML，逐个 commit 会产生大量噪音提交），要么自建 diff+branch+merge 引擎。对 floating 批注画布（DOM 层）无天然 diff——HTML 文本级 diff 会把属性顺序、空白、脚本标签当成实质变更，语义合并基本不可行。

### G5 兼容
弱。round 天然是线性递增的 confirm 门（ADR-0013 事务），分支会打破"单线程权威 + 同 round 绑定不可覆盖"的假设；git 语义（rebase/merge）对 G5 门没有新增价值。git 在这里只适合当底层存储（快照进 git 对象），不适合当产品语义。

### 用户心智模型
git（开发者工具）。"本地版本控制"四个字最容易让人想到它，但那是开发者直觉，不是设计反馈循环直觉。

### 契合度
**低** — 单用户 round 循环没有 merge 场景，HTML 文本 diff 噪音大，接入成本远超收益；jj 的自动快照值得偷思想（见 §7），但不必引入整个 VCS。

---

## 2. Patch 式（pijul / Darcs）

### 定义
以 pijul 为代表：patch（变更）是第一公民而非快照。patch 是可交换（commutative）对象——独立 patch 任意顺序应用结果一致，合并只在真正语义冲突时出现，无"重放冲突"。history 是 patch 的部分序，不是线性 DAG；branch ≈ channel（一组已应用 patch 的命名集合）。Darcs 是理论前身（有指数级合并问题，pijul 已解决，O(log n)）。

### 数据形态
`.pijul/` 目录，patch 图存储；patch 是结构化 diff（文本 hunk），可读性中——但版本引用靠哈希（"versions are unordered sets of patches"），无稳定人类可读命名。生态小（无 git 级 GUI / 托管，仅 nest.pijul.com）。

### 接入成本
高。patch 表达需对画布状态建模成可交换操作，对 DOM/HTML 原型无现成模型；生态工具缺失意味着要自建大量胶水。

### G5 兼容
弱。与 CRDT 相似提供"自动合并"，但当前是单线程 round 循环，不存在需要合并的并发流；pijul 的数学严格性用不上。

### 用户心智模型
git（但更抽象，patch 理论对非 PL 用户几乎不可见）。

### 契合度
**低** — 为分布式协同设计的 patch 理论对本地单用户 confirm 循环是过度工程，且生态最小。

---

## 3. 快照列表式（snapshot list / Time Machine 模型）

### 定义
每次"保存点"落一份不可变快照，快照之间**不存 diff**；提供列表浏览 + 还原 + 清理策略。代表：macOS Time Machine（APFS 快照，O(1) 创建、block 级 COW，保留策略 hourly×24h / daily×1月 / weekly 之后，老化自动修剪）；Figma 的 autosave checkpoints（自动时间点，非命名）；Sketch 的单文件 .sketch + 版本历史。还原即整体回滚到某快照，**非破坏性**（Figma 还原后当前版仍留在历史里）。

### 数据形态
目录 + 每快照一个文件（`round-{N}.html` 式），或内容寻址快照对象；APFS 是 b-tree XID（`tmutil listlocalsnapshots`），人类"看到"的是时间线列表而非磁盘格式。HTML 快照人类可读、可 diff（尽管噪音大）、可离线归档——与 markdown 追踪仓库天然兼容。

### 接入成本
低。现状 `round-N.html` 已是快照列表；补三步即达：① 命名（round 成功后打"round 4 已确认"式标签）；② 列表浏览 UI（sidebar 时间线，比 Figma 版历史还简单）；③ 还原（整体回滚某 round 的原型）。无需新引擎。

### G5 兼容
高。round 就是天然快照点：`confirm` 前快照 + `confirm` 后打命名版本，正好对应 Figma "里程碑才命名"的最佳实践；还原 = 回退到某 round 的确认前状态重新迭代。与 `decision-report.md` 的 report_ref 可互相引用。

### 用户心智模型
Time Machine / Figma 版本历史（照片墙式，非破坏性回看）。

### 契合度
**高** — 现状已是快照列表，补齐命名 / 浏览 / 还原即达，且全人类可读，与仓库 markdown 追踪一致；代价是 HTML 全页快照不省空间，但对原型量级可接受。

---

## 4. Figma 式（named versions + branching + merge UI）

### 定义
在快照之上加**命名版本**（人工里程碑打标，"Save to Version History"）与**分支合并**：分支独立探索不碰 main，合并时产生 checkpoint 并可视化 diff / 侧边对比 / 审批流。Figma 一手细节：autosave checkpoints 自动存在、named versions 由人命名；分支不可从分支再分叉、viewer 可建分支但 editor 才能合并、分支内评论不并入 main、合并后分支归档不可恢复（撤合并 = 把 main 还原到合并前版本）。这是 UX 最重、最接近"产品级"的形态。

### 数据形态
云端中心文件 + 版本历史时间线（非纯本地）；数据二进制、服务器权威，本地只留缓存。分支在数据层是文件的独立副本。

### 接入成本
中–高。named versions 部分轻量（复用快照列表），但 branch + merge + review UI + 可视化 diff 是整块重 UX；且非纯本地（要么自建中心，要么退化为本地目录副本分支，此时 merge 退化为人工 diff）。

### G5 兼容
中。named versions 与 round 完美契合（里程碑 = confirm 通过的 round）；但 branch 语义与单线程 G5 confirm 门冲突——除非走方向 B/C（独立 Canvas 产品 / 多人），否则 branch+merge UI 是纯负担。

### 用户心智模型
Figma（设计工具用户最熟的版本形态）。

### 契合度
**中** — 取它的"命名版本"这一半：轻、契合 G5；另一半 branch/merge UI 与单线程 round 循环冲突，仅在方向 B/C 时重估。

---

## 5. 事件溯源（event sourcing / command log + replay + fork）

### 定义
保存**所有操作事件**（command/event log），当前状态是可重放投影；可 fork（从某事件后派生新分支）、可回放任意时点。亲缘现实：ProseMirror 的 history 插件——每个事务存**逆向 steps + position maps**（双栈 done/redo，内存态不持久），undo 即逆序重放；Excalidraw 场景则存 scene JSON（一事件一状态）。事件溯源的关键 UX 是**回放浏览器**：step 到任一时点、fork 出"如果当时走了另一条路"。

### 数据形态
append-only log：目录每事件一文件（现状 `decision-round-{N}.json`）、JSONL、或 SQLite 表；人类可读（JSON/文本）。重放得到任意时点状态；体积小（只存增量语义，不存全页）。`log.md` 已是投影的例子。

### 接入成本
中。现状已是 append-only entry + log.md 投影——真正的成本在把"round"泛化为"事件"并补两个能力：**replay API**（`state_at(round_N)`，把 decision 链重放回原型+反馈组合）与 **fork API**（从某 round 派生替代方案，天然支持"备选方案对比"——正是 02 ticket 里 Figma 分支的本地替身）。不需要新存储模型，是现有事务层的**语义扩展**。

### G5 兼容
高。decision/confirm 天然是事件：G5 门通过 = 一个 tagged event；"回放到 round 3 重做" = replay 到该事件的 binding；"比较两个方案" = fork 两条链。与 round 递增、report_ref 绑定、同 round 不可覆盖等不变量零冲突。

### 用户心智模型
git 的 rebase/checkout 类比 + 时间线（比 git 简单，因为事件是语义化的"round"而非文件 blob）。

### 契合度
**高** — 当前 `decision-round-N.json` 就是事件日志雏形、`log.md` 就是投影；补 replay/fork 即把"版本控制"升维成产品语义能力，迁移成本最低且与 G5 不变量完全一致。

---

## 6. CRDT / OT（Yjs / Automerge / ProseMirror collab）

### 定义
协作优先模型：文档是共享 CRDT（Y.Map/Y.Array/Y.Text/Y.XmlFragment），本地是"我的 replica/view"，每个操作带 (clientID, clock) 唯一 ID + tombstone，任意顺序应用必收敛；无显式 merge。OT（ProseMirror collab）由中心 authority 排序 rebase。2026 现状：CRDT 已胜出 OT（谷歌、Figma 自家 canvas 都在用 CRDT 类实现）；Automerge 的 change DAG 提供类 git 的 fork/merge/history（每 change 有 hash + 父依赖），Loro 把 time travel 做成一等能力。

### 数据形态
二进制（Yjs `encodeStateAsUpdate` 逐字符 3–20 字节，RLE 压缩；Automerge `.save()` 二进制 + change DAG）。**不可人类可读**，持久化走 IndexedDB / bytea / S3 快照 + WAL。历史随文档线性增长，需 GC（`encodeStateAsUpdate` 压缩）。

### 接入成本
高。引入库 + 把画布/原型状态建模成共享类型；对当前 DOM 批注覆盖层无现成映射；且 CRDT 是文档语义，不是"round/decision"语义。

### G5 兼容
弱。G5 是**人工确认门**，不是并发编辑场景；CRDT 的自动合并在单用户循环里零价值。仅当未来走方向 B（多人可视化画布）才进入考虑。

### 用户心智模型
Google Docs 实时协作——没有"版本"概念，undo/redo 是 Y.UndoManager，版本 = 最近一次同步，不贴近"回看某轮设计"。

### 契合度
**低** — 为多人实时协作设计，二进制不可读、与 markdown 追踪仓库不兼容；当前单用户 confirm 循环用不上，留作方向 B/C 的远期选项。

---

## 7. 多维对比表

| 形态 | 存储模型 | 磁盘形态 | 人类可读 | 接入成本 | G5 兼容 | 心智模型 | 契合度 |
|---|---|---|---|---|---|---|---|
| 1. Git 式 | snapshot + 三路合并 | `.git`/`.jj` 二进制 | 工作树可读 | 高 | 弱 | git | 低 |
| 2. Patch 式（pijul） | commutative patches | `.pijul/` 结构化 diff | 中 | 高 | 弱 | git（更抽象） | 低 |
| 3. 快照列表式 | immutable snapshot list | 每快照一文件 / APFS XID | 高 | 低 | 高 | Time Machine / Figma 版历史 | 高 |
| 4. Figma 式 | named versions + branch | 云端二进制 | 低（云端） | 中–高 | 中 | Figma | 中 |
| 5. 事件溯源 | append-only log + replay/fork | 每事件一 JSON / JSONL | 高 | 中 | 高 | git checkout + 时间线 | 高 |
| 6. CRDT/OT | op-based CRDT / OT | 二进制 update + tombstone | 低 | 高 | 弱 | Google Docs | 低 |

---

## 8. 建议倾向（初判，不锁定）

- **不要**引入 git/pijul/CRDT 作为产品语义：单用户 round 循环没有 merge/并发场景，HTML 无语义 diff，二进制格式与 markdown 追踪仓库相悖。
- **推荐的两个高契合方向**（可叠加，非互斥）：
  1. **事件溯源**（§5）——当前 `decision-round-N.json` + `log.md` 已是雏形，升级 = 补 replay（`state_at(round_N)`）+ fork（替代方案对比），是"本地版本控制"最小且最契合 G5 的落地形状；
  2. **快照列表式 + 命名版本**（§3）——`round-N.html` 已是快照，补命名 / 列表浏览 / 非破坏性还原，即拿到 Figma 式版本历史中**契合度最高的那一半**，UX 与心智模型最直观。
- **偷 jj 一个思想**：working copy 自动快照（每次操作自动落盘）可作为"每 round 自动快照 + 不丢状态"的实现策略，无需引入整个 VCS。
- Figma 式 branch/merge UI（§4 另一半）与 CRDT（§6）留待方向 B/C 重估，不进入本次目的地候选。

> 初判终止于此。最终形态选择（单形态 / 混合 / 各自粒度）是 grilling ticket 的裁决范围。
