# Fill surface (数据导出入口)

Static fixture stand-in for the Fill surface. The synthesized surface implements the decision report: toolbar with a single primary batch-export Button (busy state while exporting), Table list with stable comparison columns, bounded export dialog with column-scope checkboxes, and a page-level toast for cap-limit notices. The R4 repair in this walkthrough fixed the toast (role=alert + readable name including the cap value) and the busy/disabled guard on the export trigger.
