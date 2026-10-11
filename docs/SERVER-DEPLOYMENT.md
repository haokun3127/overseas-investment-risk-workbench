# 独立服务器部署

状态：已准备隔离部署配置；实际服务器地址、权限及访问方式待提供，尚未部署到用户服务器。

## 隔离方式

`compose.server.yaml` 使用独立项目名 `risk-workbench-isolated`，与原有 `compose.yaml` 分开启动。代码和依赖在镜像中，资料保存在该项目独立的 Docker 数据卷，容器有独立网络和进程空间，默认限制 1 CPU、1GB 内存与128个进程。默认服务端口为服务器回环地址18000，由反向代理或 SSH 转发访问。

这是应用级容器隔离，仍共享宿主机内核；若要求独立操作系统，应另选虚拟机。实际资源限制、端口、目录及项目名需要结合服务器现有服务确认。

## 服务器信息与连接

已提供公网服务器 `47.108.51.138`、SSH端口22和用户名 `root`，系统版本及Docker状态待确认。不要在聊天中提供密码、私钥或 API 密钥。当前云环境的TCP通道仅支持已授权的VPN私网目标，不能直接SSH到这个公网地址；可由用户本机安全登录后执行部署命令。如需云任务直接代操作，应提供受支持的私网连接及安全认证配置，而非仅添加HTTP域名规则。

连接后先只读检查系统、可用资源、现有容器、端口和目标目录，再确定部署位置。以下路径和端口是建议值，实际操作前检查占用，不覆盖现有部署、密钥或数据。

## 首次部署步骤

服务器需已有可用的 Docker Engine 与 Compose v2。安装 Docker、修改防火墙或现有代理配置应根据实际服务器状态处理，不预设已经安装。

1. 在独立目录（建议 `/opt/risk-workbench-isolated`，也可用登录用户的独立目录）准备当前源码。记录完整 Git提交及镜像标签，不将现有项目原地替换为本项目。
2. 在未存在 `.env` 的情况下从 `.env.example` 创建，权限设为600；已有配置不要覆盖。由用户在服务器安全配置处填写检索及分析密钥。
3. 验证独立项目名及18000端口未被占用。按实际资源可调整 `WORKBENCH_CPUS`、`WORKBENCH_MEMORY` 和 `WORKBENCH_PORT`。
4. 从代码目录执行：

```bash
docker compose -f compose.server.yaml config --quiet
docker compose -f compose.server.yaml build
docker compose -f compose.server.yaml run --rm workbench python -m scripts.manage init-admin
docker compose -f compose.server.yaml up -d --wait
```

首次部署也可执行 `bash scripts/deploy_isolated.sh`。脚本先检查Docker、现有项目资源及端口，保留已有`.env`，随后构建、在本机终端初始化管理员并启动；如发现已有独立环境则停止操作，不自动覆盖。只做预检可执行 `bash scripts/deploy_isolated.sh --check`。

管理员初始化通过终端的隐藏输入进行，不写入口令到脚本、日志或聊天。不要运行 `docker compose config` 的完整输出，以免展开应用密钥；使用 `config --quiet`。

应用的初始管理员检查只接受本机请求；容器内通过服务器侧命令初始化管理员，再由浏览器登录。环境初始没有模型和检索密钥时，可先验证页面及基础资料流程，不宣称真实分析已完成联调。

## 访问方式

- 本人访问：SSH 本地端口转发至服务器 `127.0.0.1:18000`，容器端口不对公网监听。实际转发命令在用户名、地址和SSH端口确定后给出。
- 内网或域名访问：在现有代理中添加独立域名的 HTTPS 路由，转发至服务器 `127.0.0.1:18000`，保留原始 Host、配置访问控制和上传限制。HTTPS模式将 `.env` 中 `SECURE_COOKIE=true`，重建应用容器后检查登录会话。
- 不默认创建新的公网入口、不替换现有站点、不执行清空防火墙或全局 Docker 清理。

## 验证、备份与回退

部署验证包含健康接口返回内容、首页与静态资源、未登录访问受保护接口被拒绝、管理员登录、隔离库内合成资料导入/检索以及重启后的数据保留。若提供真实供应商配置，再分别验证检索和分析连接。测试不使用服务器上已有业务数据。

使用应用 README 的备份与恢复方法。备份前停止该独立工作台以保证数据库及附件一致；外部备份目录和密钥配置分别保存。需要备份的不是只有SQLite文件，还包括上传文件及网站来源版本记录。

停止环境使用：

```bash
docker compose -f compose.server.yaml stop
```

不使用 `down -v` 删除持久化数据。更新时保留原镜像标签和升级前备份，验证新版本后再切换；涉及数据库结构的回退先评估备份兼容性，不能仅依赖旧镜像覆盖运行。

## 云工作区中的构建验证

云环境安装依赖需使用平台代理和CA信任。Dockerfile 支持仅在构建步骤挂载CA，不将证书打包进镜像。使用受支持的本地Docker守护进程和继承的代理配置：

```bash
docker --host=unix:///var/run/docker.sock build \
  --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -t risk-workbench-isolated:validation .
```

无代理的用户服务器无需提供这个构建 secret，仍使用正常TLS校验。云环境构建或容器验证成功不代表已连接或部署到用户服务器。

2026-10-11 云工作区验证：Python3.13镜像构建、非root运行、只读文件系统、CPU与内存限制、健康接口、管理员登录、知识资料导入/检索、网站接口及容器重启后数据保留通过。没有访问用户服务器，实际部署仍待服务器系统和Docker状态确认。
