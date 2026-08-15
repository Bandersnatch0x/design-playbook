<!-- run-profile: v1 -->

```yaml
tier: P1
criteria:
  - decided-fields: none — bind snapshot must stay consistent (single owning-layer fix)
  - spec-touch: read-only; R2 line patches only (L4/L5 rows), no new L6 top-level items
  - blocking: <= 1, single owning layer
  - routes: R4/R5 (+R2 line) only
  - decision-tier: none — any substantive choice escalates
  - shaping: no session (bind fast path)
confirmed_by: user + 2026-08-14T12:05:00Z
skipped:
  - preview: adapter absent, no E-tier decisions (G5 not triggered)
upgrades:
  - 2026-08-14T12:40:00Z E5 added criterion l6.c4 + R1 finding beyond the P1 face -> P2 (incremental shaping session opened, DD-0101 recorded, artifacts kept)
```

# 空数据集导出修复 + 列范围升档 — plan

## 受理记录（P1 定档）

- 用户请求：「修掉空数据集导出没反馈也不出文件的问题」——单 blocking、R4 路由、
  零声明触碰预期 → P1 初判；档位确认并入指令回应。
- 跳过清单：成形会话（P1 bind 快速通道）、设计决策（无实质选择）、preview
  （适配器缺席）。

## 升档事件（W10）

- 评审走查发现「只导出选中列」用户请求为无主发现（R1，E1）；经用户裁决新增判据
  `l6.c4` —— 契约 diff（bind 后新增判据）越出 P1 允许面（E5）→ 立即升档 P2：
  补开增量成形会话（S1 直达 S3，见 `shaping/`）、补 R 档决策 DD-0101、
  过 G9/G10；已产工件全部保留（over-compliance 不回退）。

## ui-picker 输入包

- scene hints: console-tight 运营主列表（同上轮）。
- constraints: 复用既有表格与导出面板；不新增全局工具栏。
- exclusions: 不引入卡片墙；不做营销式 hero。
