# 海外投资风险工作台 · 交接说明（2026-11-12）

给另一台电脑上的 Codex：先完整读本文件，再读 `docs/` 下按日期最新的几份记录，然后再动手。

## 1. 代码与分支

- 仓库：https://github.com/haokun3127/overseas-investment-risk-workbench
- 当前工作分支：`codex/optimize-workflow-20261024`（包含截至 r12 的全部改动）
- 线上版本：`20261112-workflow-r12`
- 拉取：
  ```powershell
  git clone https://github.com/haokun3127/overseas-investment-risk-workbench.git RAG
  cd RAG
  git checkout codex/optimize-workflow-20261024
  python -m venv .venv
  .\.venv\Scripts\pip install -r requirements.txt
  ```
- 不在 Git 里的内容（`.gitignore` 排除）：`.env`、`data/`、`qa/`（本地测试副本、案例回放结果）、`*.docx`。需要时从服务器取，或由用户单独拷贝。

## 2. 服务器

- SSH：`ssh root@47.108.51.138`（密钥登录；新电脑需要用户把公钥加到服务器，或用户自行提供密码，**密码不写入仓库**）
- 网站：https://47.108.51.138/rag/ ，管理员账号 `admin`（密码由用户提供）
- 代码：`/opt/rag-workbench/current -> releases/20261112-workflow-r12`
- 数据：`/var/lib/rag-workbench/risk.db`、`vectors.db`；配置 `/etc/rag-workbench/workbench.env`（含模型密钥，**不要打印**）
- 服务：`rag-workbench.service`（127.0.0.1:8780，Nginx 反代 /rag/）
- 同机其他服务，**不要动**：`danzishi-agent`、`atrust-watchdog`、`aTrustDaemon`、`atrust-core-headless`、`wuye-dashboard`
- 最近备份：`/opt/rag-workbench/backups/pre-20261112-legal-r12/`
- 从服务器拉最新数据到本地（只读复制）：
  ```powershell
  scp root@47.108.51.138:/var/lib/rag-workbench/risk.db .\data\risk.db
  scp root@47.108.51.138:/var/lib/rag-workbench/vectors.db .\data\vectors.db
  ```

## 3. 硬性约束

- **服务器内存只有约 3.4GB，禁止在服务器上跑模型批量分析、批量案例、整库嵌入。** 之前因 OOM 失联过。批量工作在本地跑，结果以“追加”方式同步（参考 `scripts/deploy_legal_r12.py`）。
- 部署方式：复制上一个 release 为新 release，替换少量文件，停服务→备份→写数据→切换软链接→启动→健康检查，失败自动回滚。参考 `scripts/deploy_legal_r12.py`、`scripts/deploy_requirements_r11.py`。新部署要改 `app/meeting.py` 的 `VERSION` 和 `web/index.html` 的 `app-version`。
- 不改系统代理；本地调用模型需要时单进程走 `http://127.0.0.1:7897`。
- 不打印 `.env`、`workbench.env`、`auth.json` 等任何凭据。

## 4. 用户偏好

- 页面不出现任何内部标签：S1/S2、L1、客户测试、已抓取、待核验、未授权 AI 等。14 类业务风险分类保留。
- 风险等级：红、黄、蓝三级，绿色＝无风险；无法匹配的类型叫“其他”。
- 界面简洁实用，直接修、直接验证、直接部署，已授权的事不要反复确认；汇报区分“已验证”和“未验证”。
- 用中文沟通。

## 5. 本轮（r12）做了什么

- 导入 4 部印尼官方法规（资料 109–113）：贸易部长条例 2023/31、政府条例 2023/36、2025/8、1999 年第 5 号竞争法。原文 PDF 在本地 `qa/requirements-audit-20261112/legal/`（未进 Git）。
- `app/jobs.py`：分析时按事实另做一次“只查印尼法律”的检索（`_with_legal_hits`）。
- `app/model.py`：对策的法律依据核验不过时只撤掉该条依据（`basis_withheld`），不再整份分析作废；法规条款按 Pasal/款/项/BAB 切分，引文保持原文精确子串。
- 19 个参考案例本地重跑，判断/分类/等级与之前 19/19 一致；TikTok 社会商务事件对策已挂上第 21 条第 3 款原文。
- 测试：`tests/test_legal_retrieval_merge.py` 及相关套件通过。

## 6. 待办

- 其他案例法律依据覆盖率低：需要补充对应官方法规原文（BPK、peraturan.go.id、KPPU 当时访问失败，创造就业法修订文本缺）。
- TikTok 事件新分析版本回到“待复核”，需业务人员重新复核。
- 文书生成：等对方提供正式文书分类标准和模板样本。
- `scripts/route_binding_check.cjs` 第 74 行版本断言过时，是检查脚本问题，不是网站故障。

## 7. 相关文档

- `docs/` 下 2026-11-11、11-12 的整改与验收记录
- 用户桌面 `RAG项目/项目文档/`（Word 版需求、技术文档，未进 Git）
