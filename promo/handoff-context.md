# 众声 Voices — 项目交接文档

> 粘贴到新对话开头即可无缝继续。最后更新：2026-03-18。

**最新会话总结**：`docs/HANDOFF-2026-03-18.md`（广场动态、融合流、布局讨论、待办事项）

---

## 项目概况

「众声 Voices」— 知乎讨论理解工具。用户选一个知乎热榜话题或粘贴链接，AI 读完高赞回答，提炼对立观点，生成两个角色在逆转裁判风格法庭里辩论，最后揭示隐藏共识。刘看山当审判长。

参加第 2 届知乎 × Second Me Reconnect Hackathon，窗口 2026-03-16 至 2026-03-20。

- 线上地址：https://zhongsheng.ai-builders.space
- GitHub：https://github.com/danielzheng1986726/zhongsheng
- 当前部署版本：2.1.0（`/health` 可验证）

---

## 架构

```
app.py              — FastAPI 入口，挂载路由和静态文件
routers/auth.py     — Second Me OAuth2（登录/回调/登出/me）
routers/api.py      — 业务 API（热榜/辩论生成/theater/plaza/unified-feed/seed/记忆写入）
services/debate.py  — 辩论编排核心（阵营分析 → 剧本生成 → SSE 流式输出）
services/llm.py     — 多模型 fallback 封装
services/zhihu.py   — 知乎 Open API（热榜/搜索/圈子发布/评论/点赞）+ 文件缓存
services/secondme.py — Second Me API（OAuth token 交换/用户信息/聊天/记忆写入）
static/index.html   — 全部前端（单文件，原生 JS，无框架）
```

---

## 关键技术决策

| 决策 | 选择 | 原因 |
|------|------|------|
| LLM 阵营分析 | MiniMax-M2.5-highspeed | 赞助代金券，13s 完成 |
| LLM 剧本生成 | grok-4-fast | MiniMax 无法处理重 JSON prompt（52s 后断连），grok 无审核 |
| LLM fallback | deepseek → gpt-5 | deepseek 政治话题审核激进，gpt-5 需 max_tokens>=1000 |
| 持久化 | 内存 + 知乎圈子 | 无数据库，容器重启丢数据，需重新 seed |
| 圈子发布 | 仅 seed 触发 | 普通用户辩论不自动发圈子，避免刷屏 |
| 部署 | AI Builder Space API | 自动部署不可靠，用 `POST /backend/v1/deployments` + `--http1.1` |
| OAuth redirect_uri | 硬编码 fallback | 平台注入 BASE_URL 是 koyeb.app 内部地址，代码检测到 `.koyeb.app` 就忽略 |

---

## 部署操作手册

```bash
# 1. 推代码
git push origin main

# 2. 触发部署（自动部署不可靠，用 API）
curl --http1.1 -s -X POST "https://space.ai-builders.com/backend/v1/deployments" \
  -H "Authorization: Bearer sk_cd7e78cf_ccffdc35dfb8077af585ed45225716a7fc76" \
  -H "Content-type: application/json" \
  -d '{"repo_url":"https://github.com/danielzheng1986726/zhongsheng","service_name":"zhongsheng","branch":"main","port":8000}'

# 3. 等 5-10 分钟，验证版本
curl https://zhongsheng.ai-builders.space/health
# 期望: {"status":"ok","version":"2.1.0"}

# 4. 验证 OAuth redirect_uri
curl -s -o /dev/null -w '%{redirect_url}' https://zhongsheng.ai-builders.space/api/auth/login
# 期望: redirect_uri 包含 zhongsheng.ai-builders.space（不是 koyeb.app）

# 5. 重新 seed 剧场（容器重启后内存清空）
curl -X POST https://zhongsheng.ai-builders.space/api/admin/seed -H 'Content-Type: application/json' -d '{"count":3}'
```

---

## 当前状态（2026-03-17）

### 已完成
- 全部产品功能（辩论生成、法庭动画、共识分析、海报、分享、OAuth、旁听席）
- 手机端适配（@media max-width 480px）
- OAuth redirect_uri 修复
- 圈子自动发布改为仅 seed 触发
- 音效按钮移入法庭、知乎原帖链接
- 知乎 #AI上新 文章已发布（知乎科技运营林珍妮承诺推流）
- reconnect-hackathon.com 项目已提交
- OAuth 端到端验证通过

### 待完成
| 优先级 | 事项 | 说明 |
|--------|------|------|
| P1 | Demo 演示准备 | 预选稳定话题，确保现场不翻车 |
| P1 | 推广引流 | OAuth 量是评奖指标。渠道：参赛群、朋友圈、知乎公域 |
| P2 | 融合流布局 | 热榜+广场混排，Web/移动响应式。详见 docs/HANDOFF-2026-03-18.md |

---

## 踩过的坑

1. **AI Builder Space 自动部署不触发**：push 到 main 后经常不自动部署，即使 dashboard 显示 Healthy。必须用 Deploy API 手动触发。
2. **HTTP/2 framing error**：Deploy API 必须加 `--http1.1`，否则 exit code 16。
3. **BASE_URL 注入**：平台注入的 BASE_URL 是 Koyeb 内部地址（`http://ai-builders-9-yage-*.koyeb.app`），导致 OAuth redirect_uri 错误。`routers/auth.py` 的 `_base_url()` 检测 `.koyeb.app` 并忽略。
4. **MiniMax 断连**：MiniMax-M2.5 在复杂 JSON prompt 时 52s 后 RemoteProtocolError，所以剧本生成改用 grok-4-fast。
5. **圈子帖子稀释**：圈子里有其他人的帖子，导致 feed 数据源不纯，改用服务端内存缓存 `completed_debates`。
6. **gpt-5 空响应**：不设 max_tokens 或设太小会返回空内容，必须 >= 1000。

---

## 知乎运营资源

知乎科技运营林珍妮（DM 联系过）：
- 提供 #AI上新 话题标签推流
- 建议写长文发到话题下，她帮推
- 文章已发布，配了宣传海报

---

## 关键文件快速定位

| 需求 | 文件 | 关键位置 |
|------|------|---------|
| 辩论生成逻辑 | services/debate.py | `generate()` 函数 |
| LLM 调用/fallback | services/llm.py | 多模型 fallback chain |
| 前端全部 UI | static/index.html | 单文件，~2200 行 |
| OAuth 流程 | routers/auth.py | `_base_url()` + login/callback |
| 知乎 API 签名 | services/zhihu.py | `_sign_headers()` |
| 部署配置 | Dockerfile | CMD 用 sh -c 展开 $PORT |
| 推广素材 | promo/ | 文章草稿、海报、话术模板 |
