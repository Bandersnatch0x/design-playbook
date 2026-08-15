# Fill surface (空数据集导出修复 + 列范围升档)

Static fixture stand-in for the Fill surface. The R4 repair added the empty-blocked pre-check on the export trigger (toast: 「无可选行」 with the trigger disabled while the dataset is empty), and — after the P2 escalation — the column-scope checkboxes in the export dialog drive a selected-columns-only CSV export. Busy/disabled guard and cap-limit toast behavior are retained from the prior run.
