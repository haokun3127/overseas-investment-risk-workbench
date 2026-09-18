# 海外投资风险识别与智能分析工作台

本地部署的一期技术验证系统，面向印度尼西亚制造业。业务系统和资料存储在本地，先接入可配置的大模型 API，再根据甲方服务器资源替换为本地推理服务。

## 已实现

2026-09-12 已补强各模块的业务交互，详见 [功能完善记录](docs/WORKFLOW-UPGRADE.md)：风险台账导出、复核历史、资料与任务筛选、会话内草稿恢复、表单式风险规则、合成内容模型连接检查、准备清单及操作记录。

- 中文 Web 工作台：风险总览、列表、详情、来源追溯及业务复核。
- Excel / CSV / Word / 文本型 PDF / TXT / Markdown 导入和手工录入；逐行错误、重复检查及原文件保存。
- 本地轻量知识库：中文双字词和英文单词 BM25 检索，不依赖外部向量服务。
- 可配置 Chat Completions 兼容 API；外部 / 本地两种模式，真实调用失败不会返回演示分析。
- 单进程持久化任务队列；任务进度、失败重试、重启恢复状态；分析版本、规则、证据片段及模型信息记录。
- 分类范围校验、连续原文引用校验，拒绝不匹配的来源。每条风险必须引用输入资料。
- 单管理员登录、密码派生存储、会话有效期、同源请求校验、基础审计和备份恢复命令。
- 四条可手动载入的**虚构演示案例**，仅供查看交互，不属于真实模型输出。

## 本机启动

建议 Python 3.11–3.13。本开发环境使用 Python 3.13；运行验证以 requirements-lock.txt 中版本为准。

Windows PowerShell，在项目目录运行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env   # 仅首次创建；已有 .env 时不要覆盖
.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 。首次访问在服务器本机设置至少10位的管理员密码。当前工作目录已经准备好 `.venv` 和空白 `.env`，双击 `start.cmd` 即可在后台启动服务并打开浏览器；也可在 PowerShell 中运行 `./start.ps1`。脚本会等待服务就绪，重复启动会复用已运行的工作台，关闭启动终端不影响后台服务。运行日志保存在 `logs/`。电脑重启后需再次启动；需要查看实时日志时使用 `./start.ps1 -Foreground`（须先停止已有服务）。

Linux：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
cp .env.example .env
.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

仅运行一个 Uvicorn worker。本版本的后台队列不适用于多进程或多副本部署。需要局域网访问时，在管理员初始化后配置内网监听、访问控制和 HTTPS 反向代理；HTTPS 部署将 `SECURE_COOKIE=true`，代理须保留正确 Host。不要直接暴露至公网。

## 接入真实模型 API

在服务器 `.env` 中填写：

```dotenv
MODEL_MODE=external
MODEL_BASE_URL=https://服务商实际API基础地址/v1
MODEL_NAME=实际模型标识
MODEL_API_KEY=实际密钥
MODEL_TIMEOUT=90
MODEL_JSON_MODE=true
```

服务必须兼容 `POST {MODEL_BASE_URL}/chat/completions` 的 messages 与 choices 返回结构。若供应商不支持 `response_format`，设置 `MODEL_JSON_MODE=false`；仍要求输出合法 JSON。API 地址和模型标识不预设厂商。模型服务变更后重启后端。

密钥不通过前端设置或返回。不应发到聊天、提交 Git 或写入日志。模型设置页显示“已配置”仅说明必要配置存在，不等于真实接口已验证。

真实测试步骤：

1. 在“模型与规则”中按甲方标准修改规则版本、分类及红橙黄等级，确认规则。
2. 导入允许测试的资料。外部模式需要明确勾选该资料允许发送外部模型；知识库参考资料同样遵守此限制。
3. 在资料列表点击“分析”，或批量选择后提交。
4. 在分析任务查看进度。成功后核验事件、等级、依据与建议；失败时先解决配置或资料问题再重试。
5. 修改分类、提示词或模型后，重新分析同一资料生成新版本，历史版本保留；失败任务不覆盖原结果。

每条资料的“查看原文”中可更改外发授权。已发送的数据无法通过取消授权撤回；存在待处理或运行任务时禁止修改该待分析资料的授权。该系统不自动访问来源链接、不采集互联网资料。

## 后续本地模型部署

```dotenv
MODEL_MODE=local
MODEL_BASE_URL=http://甲方内网推理地址:端口/v1
MODEL_NAME=实际部署模型标识
MODEL_API_KEY=本地服务需要时填写
```

本地模式只接受解析到回环或内网地址的服务，不自动回退外部 API。部署环境应固定受信任的内网地址，使用防火墙阻断非必要外网出口；应用层地址检查不替代网络隔离。

模型选型仍需甲方 CPU、内存、GPU 与显存、操作系统、磁盘、网络和负载信息。模型能启动不等于验收通过，需比较分类一致性、识别召回率、引用正确性、分析质量、长文本效果、时延和资源占用。完全离线验证还需准备离线依赖和模型权重。

## 文件与检索限制

- 单文件10MB；CSV / Excel 每次最多500条；单条正文60000字符；PDF最多200页。
- 表格列：`标题,时间,来源,正文,原始链接`，也支持 `title,date,source,body,url`。时间为 YYYY-MM-DD，可为空。仅标题与正文必填。
- Word 仅支持 `.docx`，Excel 仅支持 `.xlsx`；宏文件和旧二进制格式需先转换。
- 扫描件不含自动 OCR，加密和无法提取文本的 PDF 会提示失败。复杂版式的解析顺序需人工抽查。
- 引用以保存正文中的字符区间定位；PDF正文保留页码标识。DOCX 表格在段落后提取，复杂文档并非完整视觉版式还原。
- 长资料分为2400字符片段逐段分析。可能遗漏跨段关联或产生相似事件；详情会提示人工核验。当前只合并标题和首条引用均相同的事件。
- BM25 是轻量词项检索，不是语义向量检索；同义表达、跨语言检索和大规模知识库可作为后续增强。
- 原文连续引用校验不能证明模型推理正确，仍需甲方业务人员复核。当前不自动判断法规有效性，参考资料应由甲方筛选更新。

## 数据与备份

默认目录：`data/risk.db` 保存业务数据、分析、规则、会话和审计；`data/uploads/` 保存原文件。演示与测试分离：浏览器自动化使用 `qa/ui-data`，不初始化正式工作台的管理员，也不向正式库写入案例。

为获得资料与附件一致的快照，停止服务后执行：

```powershell
.venv/Scripts/python.exe -m scripts.manage backup --destination C:/backups/risk-20260909
.venv/Scripts/python.exe -m scripts.manage restore --source C:/backups/risk-20260909 --destination C:/risk-restored
```

恢复只允许写入不存在的新目录，检查 SQLite 完整性并清除旧会话。之后在 `.env` 设置 `DATA_DIR=C:/risk-restored` 并启动服务。`.env` 单独安全备份，不包含在数据备份中。

## Docker 交付方式

```bash
docker compose build
docker compose run --rm workbench python -m scripts.manage init-admin
docker compose up -d
```

Docker 路径通过交互命令初始化管理员，因为容器内看到的浏览器地址通常不是回环地址。访问 http://127.0.0.1:8000 。镜像使用非 root 用户和持久化卷；此配置尚需在甲方 Docker 环境构建验证。镜像构建需要联网安装依赖，完全离线环境需提前准备镜像。

## 验证与测试

```powershell
.venv/Scripts/python.exe -m pytest -q
```

测试覆盖认证与同源限制、导入及格式错误、外发边界、知识检索、来源校验、任务重试、版本保留、演示隔离及真实 HTTP 传输协议。测试模型是受控的本地 HTTP 模拟服务，不是实际供应商模型，不能据此宣称业务分析效果已通过。

`scripts/ui_test.cjs` 使用 Playwright 对隔离的8001测试服务执行浏览器操作。需要自行安装 Playwright 或通过 `PLAYWRIGHT_MODULE` 指向可用包，并有 Chrome；测试口令仅用于 `qa/ui-data`。截图和结果写入 `qa/`。

## 项目结构

```text
app/          后端、解析、检索、模型接入、队列与数据库
web/          无外部资源依赖的中文前端
tests/        后端与模型协议回归测试
scripts/      备份恢复、管理员初始化、浏览器测试
.env.example  模型配置示例
start.cmd     Windows 双击启动并打开浏览器
start.ps1     Windows 后台启动入口（支持 -Foreground）
```

## 参考接口文档

- Chat Completions 协议：https://developers.openai.com/api/reference/resources/chat
- FastAPI 文件上传：https://fastapi.tiangolo.com/tutorial/request-files/

这是一台服务器上的验证版本，尚未进行甲方真实案例验收、GPU 推理部署、高并发测试、企业级安全加固或生产级容灾建设。
