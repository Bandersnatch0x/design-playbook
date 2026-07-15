# [功能名] 交互设计 Spec

## L1 定位与意图
- 一句话定义：
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

## L5 边界条件
- 空态：
- 加载态：
- 错误态：
- 权限降级：

## L6 验收标准
- Given / When / Then：
- 设计完成定义：

---

## Worked snippet (illustrative)

For an agent-ops list: a failed item must show cause + retry (L3/L4); no-data shows a non-blank empty state (L5); without permission the dangerous action is disabled with a reason (L5); acceptance ticks each of these (L6). Adapt to the actual product; this is not a fixed domain.
