# 独立服务器部署记录

部署日期：2026-10-11（Asia/Shanghai）。
入口：https://47.108.51.138/rag/

## 环境隔离

- 系统用户/用户组：rag-workbench（禁止交互登录）。
- 代码：/opt/rag-workbench/releases/20261011-demo；current 为发布目录软链接。
- 独立虚拟环境：/opt/rag-workbench/venv（Python 3.10.12）；依赖按 requirements-lock.txt 安装。
- 数据库及上传目录：/var/lib/rag-workbench，仅工作台用户可访问。
- 配置：/etc/rag-workbench/workbench.env，root 所有，工作台组只读。
- 服务：rag-workbench.service，开机自动启动、异常自动重启。
- 后端只监听 127.0.0.1:8780，经 Nginx 的 /rag/ 入口访问。
- ProtectSystem=strict、ProtectHome、PrivateTmp、NoNewPrivileges；仅数据目录可写。
- 屏蔽 /opt/wuye_agent、/opt/danzishi-agent、/var/lib/danzishi-agent。
- 内存上限 768 MiB、CPU 配额一个核心、任务数上限 64。
- 独立会话 Cookie risk_rag_session，Path=/rag/，Secure、HttpOnly、SameSite=Strict。

## 发布与配置

Nginx 使用 /etc/nginx/snippets/rag-workbench.conf；原配置仅新增 include。
原配置备份：/opt/rag-workbench/nginx-wuye-before-rag.conf。
现有证书和证书续期配置保留，现有物业根路径和弹子石 /danzishi/ 路径保留。

为支持子路径，前端静态资源和 API 使用相对路径；后端按照 ASGI root_path 识别认证路径。
COOKIE_PATH 和 SESSION_COOKIE_NAME 默认保持本地使用方式，服务器在环境配置中覆盖。

使用全新数据库，未复制本机资料或管理员密码。服务器管理员已独立初始化，初始化明文文件在验证后删除。
管理员登录仅需密码；登录密码另存于本机私有文件，不存入本仓库或服务器发布包。
模型现已接入顺顺云 https://api.ssyun0.com/v1，使用 gpt-6.1-sol、Responses 协议、low 推理强度、store=false。密钥只保存在服务器私有配置中。

新增 4 条内置静态案例与 3 条合成 API 案例，全部 demo=1，不计入真实资料。演示规则 demo-validation-v1 仅供展示，不是正式业务标准。

## 运维

```sh
systemctl status rag-workbench
systemctl restart rag-workbench
journalctl -u rag-workbench -n 100 --no-pager
```

修改模型服务参数：编辑 /etc/rag-workbench/workbench.env 后重启 rag-workbench。
备份前停止工作台，使用 scripts.manage backup；备份包含数据库和上传目录，配置文件另行保管。
恢复使用 scripts.manage restore 写入一个新目录，不覆盖原数据。

停用入口：删除 Nginx 中新增的 rag-workbench include，执行 nginx -t，通过后 reload nginx；
再 systemctl disable --now rag-workbench。保留数据目录供恢复。不要直接用历史备份覆盖后续其他服务的配置。

## 验证

- 本机 23 项测试通过；Ubuntu 服务器 23 项测试通过。
- 公网 HTTPS 页面、静态资源、健康检查正常。
- 管理员登录、退出、受保护 API、模板下载验证通过。
- 未登录业务 API 返回 401，Cookie 不发送到根路径。
- 原根路径返回 302、/danzishi/ 返回 303，与部署前一致；既有服务保持运行。
- 后端监听范围、systemd 隔离选项及资源限制已核验。
