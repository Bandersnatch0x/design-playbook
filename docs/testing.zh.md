# 测试与验证

完整执行清单由 [CI workflow](../.github/workflows/ci.yml) 维护，本文只解释选择与证据边界，不复制测试文件库存。

## 选择范围

- 仓库工具、安装与发布契约：从根目录 `tests/` 的受影响测试开始。
- 产品脚本、Preview、Evidence、Run Console：从 `packages/design-playbook/tests/` 的所属模块开始。
- 前端确认、状态同步和取证：运行实际 Chromium 回归；纯 Python 通过不能代替浏览器结果。
- 文档迁移或导航修改：运行 `python -m pytest tests/test_doc_links.py -q`，再运行 `python scripts/check_doc_links.py`。

`validate.py` 验证产品结构、声明与生成快照；`doctor.py` 检查本地安装/运行健康；链接检查验证公开导航和 Git 私有资产边界。这些结果不证明用户体验收益、双语语义一致或外部试用成功。

## 失败与报告

缺少浏览器或依赖时明确报告未跑及原因，不把 skip 计为通过。长命令使用有界超时，保留失败日志；修复后记录重跑范围，不能用此前的绿灯覆盖当前改动。

自动化回放的隔离环境与数据边界见[自动化验收](agents/automated-acceptance.md)。真实自用样本、外部试用和合成夹具分别陈述；没有用户反馈时保留未知，不补造指标。

交付记录包含命令、环境、结果和限制。原始输出可留本地 `.scratch/`；共享摘要只保留必要、脱敏的结论，不提交个人日志或 issue 副本。
