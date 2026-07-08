# Zhongsheng Voices

`zhongsheng` 是一个 FastAPI 小应用：读取知乎公开讨论，生成模拟法庭式辩论，并通过 HTTP MCP endpoint 暴露搜索、热榜、辩论读取和评论工具。

## 当前状态

- 项目处于暂停维护状态；本地修复可以继续做，部署和线上环境变量更新单独决定。
- GitHub remote 仍存在，B0 已移除当前代码中的硬编码凭证，但旧凭证仍在历史/远端层，未做 history rewrite。
- `.env`、本地数据库、知乎缓存和工具运行态不入库。

## 本地准备

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

必要环境变量：

- `SECONDME_CLIENT_ID`
- `SECONDME_CLIENT_SECRET`
- `SESSION_SECRET`
- `ZHIHU_ACCESS_KEY`

可选环境变量：

- `BASE_URL`
- `AI_BUILDER_TOKEN`
- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `MINIMAX_API_KEY`

`SECRET_KEY` 只作为旧部署兼容 fallback；新配置统一使用 `SESSION_SECRET`。

## 本地运行

```bash
python3 app.py
```

服务启动后：

- App: `http://localhost:8000/`
- Health: `http://localhost:8000/health`
- MCP discovery: `http://localhost:8000/.well-known/mcp`
- MCP endpoint: `http://localhost:8000/mcp`

## 本地验证

```bash
python3 -m py_compile app.py routers/*.py services/*.py tests/*.py
python3 -m unittest discover -s tests -q
```

测试只覆盖本地 smoke path，不调用 Second Me、知乎、AI Builder 或 Turso。
