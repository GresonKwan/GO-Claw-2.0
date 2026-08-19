# GO CLAW 自动开通服务（provisioning）

随 GO CLAW 便携包首次启动自动运行的配套服务端：为每个软件实例在 NewAPI 中
创建一个子用户、签发一张带赠送额度的专属 API Key，并把可直接落盘的
`credentials.json` 内容返回给客户端。

## 工作流程

```
客户端首次启动                     本服务                          NewAPI
instance.id(UUID) ──HMAC签名──▶ 验签/时间窗/IP限流
                                幂等查询(SQLite) ──已开通──▶ 返回存档凭证
                                    │ 未开通
                                    ▼
                                建子用户 gc-xxxxxxxx ──▶ POST /api/user/
                                登录子用户             ──▶ POST /api/user/login
                                签发限额令牌            ──▶ POST /api/token/
                                取回完整 Key           ──▶ GET /api/token/
                                    │
                                存档并返回 credentials.json 内容
```

- **幂等**：同一 instance_id 永远拿回同一份凭证（同一子用户/Key），
  重装、换电脑、重复请求都不会重复发 Key。
- **防刷**：HMAC 签名（密钥内嵌于客户端构建，可被提取，仅作第一道闸）
  + 每 IP 每日限流 + 赠送额度本身较小 + NewAPI 后台可随时禁用异常子用户。
- **权限边界**：NewAPI 管理员系统访问令牌只存在于本服务的 `.env`，
  绝不下发到客户端。

## 部署（与 NewAPI 同机）

```bash
cd scripts/provisioning
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填写配置，见文件内注释
set -a && source .env && set +a
uvicorn provision_server:app --host 127.0.0.1 --port 9100
```

建议用 nginx/Caddy 以 HTTPS 反代到 `127.0.0.1:9100`，路径如
`https://你的域名/api/provision`（客户端 `provision.json` 里的
`provisionUrl` 填完整地址）。

### systemd 单元示例

```ini
[Unit]
Description=GO CLAW Provisioning
After=network.target

[Service]
WorkingDirectory=/opt/go-claw-provisioning
EnvironmentFile=/opt/go-claw-provisioning/.env
ExecStart=/opt/go-claw-provisioning/.venv/bin/uvicorn provision_server:app --host 127.0.0.1 --port 9100
Restart=always

[Install]
WantedBy=multi-user.target
```

## 获取 NewAPI 管理员令牌

NewAPI 后台 → 个人设置 → 安全设置 → 系统访问令牌 → 生成。
`.env` 中 `NEWAPI_ADMIN_ACCESS_TOKEN` 填该令牌，`NEWAPI_ADMIN_USER_ID`
填管理员账号的用户 ID（通常为 1）。

## 运维

- 数据全在 `provision.db`（SQLite）：`provisions` 表是 instance → 子用户
  的映射，`request_log` 表用于限流。备份该文件即可。
- 查看已开通实例：`sqlite3 provision.db 'select instance_id, username, created_at from provisions where status="done"'`
- 回收某实例：在 NewAPI 后台禁用对应子用户或删除其 `go-claw-auto` 令牌。

## 测试

```bash
pip install pytest
DB_PATH=:memory: pytest test_provision_server.py -q
```
（单测通过依赖注入 mock 掉 NewAPI 调用，不需要真实 NewAPI。）
