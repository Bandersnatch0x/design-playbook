<!-- spec-schema: 1 -->

# [功能名] 交互设计 Spec

## L1 定位与意图
- 用户可见目标：
- 目标用户：
- 场景清单：
- 非目标：
- 行为边界：始终 / 询问后 / 永不

## L2 信息架构
- 空间区域定义：
- 区域边界规则：
- 内容生长规则：

## L3 核心链路
- 状态清单：
- 主链路：
- 分支链路：

## L4 组件功能细节
- 组件定位与功能清单
- 默认 / 悬停 / 加载 / 禁用 / 错误 等状态
- L4 declares control behavior only; reuse / no-internal-change constraints must name exceptions (for example, allow a minimal patch when they conflict with L5).

## L5 边界条件
- 空态：
- 加载态：
- 错误态：
- 权限降级：

## L6 验收标准
- 每条验收是一个顶层列表项，按序显式包含 `Given` → `When` → `Then`（顺序固定），并写明该条的必备证据
  - 必备证据：规划声明覆盖 / 目标视口渲染 / 交互记录或自动化检查 / 相关 test、type、lint、build（按任务适用项选择）
  - 证据为运行时状态时，命名 capture seed（要捕获的状态 + 捕获类型，如 "error-state screenshot"）；不写 selector/URL/actions
- 设计完成定义：

---

## Worked snippet (illustrative)

For an agent-ops list: a failed item must show cause + retry (L3/L4); no-data shows a non-blank empty state (L5); without permission the dangerous action is disabled with a reason (L5); acceptance ticks each of these (L6). Adapt to the actual product; this is not a fixed domain.
