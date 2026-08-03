# Ticket 03-compute — 计算主体与失真防护

Type: decision
Status: resolved
Resolved: 2026-08-03 (roundtable synthesis；用户拍板保留 repeat blocker)

保留 repeat blocker（0/20 出自本仓 gate 语料不可外推；砍半不如砍整个主题）。条件式 seam：plugin 安装态逐 run 跑 shipped `validate_run.py` 取真实退出状态；npm/pi 装不到该脚本 → gate 列填 `not checked`，永不由"产物看着齐"推 ok。门槛：含 point-back.md 的 run < 2 拒绝并报 N；无 point-back 上清单贡献 0 行。归一化一行规则（casefold + 空白折叠后逐字符相等；result != pass；count ≥ 2）；**shipped 文案是 SSOT，aggregate_runs.py normalize() 是 follower**，`tests/test_normalize_lockstep.py` 锁漂移。`_none_` 是正常结果。DX 四条防失真全收（inclusion manifest 先行 / 禁过度归一化 / manifest 诚实性提示 / rollup 逐行推出）。
