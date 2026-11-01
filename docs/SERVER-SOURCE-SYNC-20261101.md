# 线上源码同步（2026-11-01）

本次从服务器 `/opt/rag-workbench/current` 的实际目标
`/opt/rag-workbench/releases/20261029-frontend-harden` 读取源码快照。

同步范围：`app/`、`web/`、`scripts/`、`tests/`、三个 requirements 文件和线上前端加固说明。
仓库原有 README、部署模板及历史文档保留，不将它们伪称为本次线上发布包中的文件。

线上发布目录没有 Git 元数据；本次以仓库现有工作分支的提交 `f36d5ff` 为基础，
在独立分支 `codex/sync-server-rag-20261101` 同步部署文件，不覆盖主分支或其他本地分支。

排除环境配置、账号密码、API 密钥、Token、数据库、上传资料、模型文件、运行日志、
发布归档、测试缓存、旧 `.bak-*` 备份和 macOS `._*` 元数据。
本次只同步源码，不发布、不重启、不修改线上配置，也不触发真实资料分析或外部模型调用。

主要差异包含本地向量检索及指标代码、任务/检索后端更新、五级风险相关前端、网站检索与请求超时加固。
向量模块缺少可选依赖或模型时会回退，源码同步并不证明向量模型已在新环境安装或验收。

## 验证结果

- 服务器归档与当前发布目录对比一致；线上服务保持 active，未重启。
- 修改过的 JavaScript 文件通过 `node --check`；`git diff --cached --check` 通过。
- 对待推送差异执行常见私钥、GitHub Token、API Key、JWT 格式扫描，未发现匹配；
  这是规则检查，不声称覆盖所有敏感信息格式。提交清单不含运行数据或环境密钥文件。
- Windows 本机离线 `pytest -q -p no:cacheprovider`：163 通过、2 失败、2 个依赖弃用警告。
  失败一：`test_quarantine_dry_run_mismatch_and_apply` 的 POSIX `0700` 权限断言在 Windows 不成立。
  失败二：`test_complete_supplement_flow_preserves_history_and_citations` 中旧 `orange` 风险等级
  合成响应在现行五级校验下没有形成预期风险结果（实际 insufficient）。
  本次仅如实同步服务器源码，不修测试或改变业务逻辑，不宣称全量通过。
- 本机测试未覆盖生产向量模型效果、真实模型 API 或真实业务资料，不能替代业务验收。
