# Decision report — 塔罗牌浮雕显示页

design-baseline: 无既有产品基线（新页面，skip，ADR-0012 N/A）
scene: 陈列墙（collection / card wall）
density: marketing-loose（浮雕质感需展示空间；网格 4 列 × 3 行）
template: 单页陈列 + lightbox 聚焦（main = 牌阵网格，overlay = 聚焦区，top = 控制条，status = 计数徽章）
regions:
  - top bar: 标题 + 洗牌按钮 + 全部翻回按钮 + 计数徽章（status 角色）
  - main: 牌阵网格（4×3，每卡 = tarot-card 组件）
  - overlay: 单卡聚焦 lightbox（卡名/编号/牌意 + Esc/遮罩关闭）
components:
  - 卡组件 tarot-card：状态组件（card-back / card-face / focused 三态）；浮雕 = 多层渐变 + 阴影 + 内线（L6.2 证据锚）
  - 洗牌按钮：action 角色；动画期间禁用（loading tier 2）
  - 计数徽章：status 角色（已翻开 N / 12）
  - lightbox：Dialog 语义（非 Drawer——聚焦查看是模态覆盖）
  - 骨架占位：loading 态（skeleton 卡形）
  - 空态：显式文案 + 重载按钮
baseline-changes: none
risks:
  - 浮雕质感依赖纯 CSS 多层效果——不同浏览器渲染差异（保存主要风险，L6.2 以截图验证）
  - 78 张全集过重 → 用 12 张代表牌（大阿卡纳 0-11），卡名/牌意为占位文案（产品集成时换真数据源）
  - 无真牌面图片 → 卡面用 CSS 生成纹样 + 文字（不引入外部资源，自包含）
