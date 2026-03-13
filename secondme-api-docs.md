# SecondMe API Developer Documentation (Complete)

> Extracted from https://develop-docs.second.me/zh/docs on 2026-03-13
> For hackathon integration reference

---

## Overview

**Base URL:** `https://api.mindverse.com/gate/lab`

**App Registration:** https://develop.second.me/

**Capabilities:**
- Access authorized user personal information
- Access user soft memory (personal knowledge base)
- Conduct streaming conversations as user's AI avatar
- Text-to-speech generation
- Action judgment (Act) streaming
- Agent Memory event reporting

---

## Authentication

### OAuth2 Authorization Code Flow

1. User visits third-party application
2. Application redirects to SecondMe authorization endpoint
3. User grants permission on authorization page
4. Authorization server returns authorization code via redirect
5. Application exchanges code for Access Token (server-side)
6. Application uses token to call SecondMe API
7. API returns requested data

### Request Header Format

```
Authorization: Bearer <token>
```

Token format: `lba_at_xxxxx...` (OAuth2 Access Token)

### Token Types & Validity

| Type | Prefix | Duration |
|------|--------|----------|
| Authorization Code | `lba_ac_` | 5 minutes |
| Access Token | `lba_at_` | 2 hours |
| Refresh Token | `lba_rt_` | 30 days |

### Permission Scopes

| Scope | Purpose |
|-------|---------|
| `user.info` | Basic user info (name, email, avatar) |
| `user.info.shades` | User interest tags |
| `user.info.softmemory` | User soft memory (personal knowledge base) |
| `note.add` | Add notes and memories |
| `chat` | Chat functionality |
| `voice` | Voice features |

### Prerequisites

1. Register application at https://develop.second.me/
2. Obtain `client_id` and `client_secret`
3. Configure Redirect URI

---

## OAuth2 API Reference

### 1. Authorization Entry (Frontend Redirect)

**GET** `https://go.second.me/oauth/`

Redirect users for login and authorization.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `client_id` | string | Yes | Application Client ID |
| `redirect_uri` | string | Yes | Callback URL after authorization |
| `response_type` | string | Yes | Fixed value: `code` |
| `state` | string | Yes | CSRF protection parameter (random string) |

**Example:**
```
https://go.second.me/oauth/?client_id=your_client_id&redirect_uri=https://your-app.com/callback&response_type=code&state=abc123
```

**Success Redirect:**
```
https://your-app.com/callback?code=lba_ac_xxxxx...&state=abc123
```

**Error Redirect:**
```
https://your-app.com/callback?error=access_denied&error_description=User%20denied%20access&state=abc123
```

### 2. User Authorization (Server-Side)

**POST** `/api/oauth/authorize/external`

**Auth:** Bearer Token (user login state required)

**Request Body (JSON):**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `clientId` | string | Yes | Application Client ID |
| `redirectUri` | string | Yes | Callback URL |
| `scope` | string[] | Yes | Permission list |
| `state` | string | No | CSRF state |

```bash
curl -X POST "https://api.mindverse.com/gate/lab/api/oauth/authorize/external" \
  -H "Authorization: Bearer <user_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "clientId": "your_client_id",
    "redirectUri": "https://your-app.com/callback",
    "scope": ["user.info", "chat"],
    "state": "abc123"
  }'
```

**Success Response (200):**
```json
{
  "code": 0,
  "data": {
    "code": "lba_ac_xxxxx...",
    "state": "abc123"
  }
}
```

**Error Codes:** `oauth2.application.not_found`, `oauth2.redirect_uri.mismatch`, `oauth2.scope.invalid`

### 3. Exchange Authorization Code for Token

**POST** `/api/oauth/token/code`

**Auth:** None (public endpoint)

**Content-Type:** `application/x-www-form-urlencoded` (REQUIRED)

**Form Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `grant_type` | string | Yes | Fixed: `authorization_code` |
| `code` | string | Yes | Authorization code from Step 1 |
| `redirect_uri` | string | Yes | Must match authorization request |
| `client_id` | string | Yes | Application Client ID |
| `client_secret` | string | Yes | Application Client Secret |

```bash
curl -X POST "https://api.mindverse.com/gate/lab/api/oauth/token/code" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "code=lba_ac_xxxxx..." \
  -d "redirect_uri=https://your-app.com/callback" \
  -d "client_id=your_client_id" \
  -d "client_secret=your_client_secret"
```

**Success Response (200):**
```json
{
  "code": 0,
  "data": {
    "accessToken": "lba_at_xxxxx...",
    "refreshToken": "lba_rt_xxxxx...",
    "tokenType": "Bearer",
    "expiresIn": 7200,
    "scope": ["user.info", "chat"]
  }
}
```

**Error Codes:** `oauth2.grant_type.invalid`, `oauth2.code.invalid`, `oauth2.code.expired`, `oauth2.code.used`, `oauth2.redirect_uri.mismatch`, `oauth2.client.secret_mismatch`

### 4. Refresh Token

**POST** `/api/oauth/token/refresh`

**Auth:** None (public endpoint)

**Content-Type:** `application/x-www-form-urlencoded` (REQUIRED)

**Form Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `grant_type` | string | Yes | Fixed: `refresh_token` |
| `refresh_token` | string | Yes | Previously obtained refresh token |
| `client_id` | string | Yes | Application Client ID |
| `client_secret` | string | Yes | Application Client Secret |

```bash
curl -X POST "https://api.mindverse.com/gate/lab/api/oauth/token/refresh" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token" \
  -d "refresh_token=lba_rt_xxxxx..." \
  -d "client_id=your_client_id" \
  -d "client_secret=your_client_secret"
```

**Success Response (200):**
```json
{
  "code": 0,
  "data": {
    "accessToken": "lba_at_new_xxxxx...",
    "refreshToken": "lba_rt_xxxxx...",
    "tokenType": "Bearer",
    "expiresIn": 7200,
    "scope": ["user.info", "chat"]
  }
}
```

**Note:** Refresh token does NOT rotate. The returned token matches the request. Valid for 30 days.

**Error Codes:** `oauth2.grant_type.invalid`, `oauth2.refresh_token.invalid`, `oauth2.refresh_token.expired`, `oauth2.refresh_token.revoked`, `oauth2.client.secret_mismatch`

---

## SecondMe API Reference

### 1. Get User Info

**GET** `/api/secondme/user/info`

**Scope Required:** `user.info`

```bash
curl -X GET "https://api.mindverse.com/gate/lab/api/secondme/user/info" \
  -H "Authorization: Bearer lba_at_your_access_token"
```

**Response (200):**
```json
{
  "code": 0,
  "data": {
    "userId": "12345678",
    "name": "用户名",
    "email": "user@example.com",
    "avatar": "https://cdn.example.com/avatar.jpg",
    "bio": "个人简介",
    "selfIntroduction": "自我介绍内容",
    "profileCompleteness": 85,
    "route": "username"
  }
}
```

**Fields:** userId (string), name, email, avatar (URL), bio, selfIntroduction, profileCompleteness (0-100), route

### 2. Get User Interest Tags (Shades)

**GET** `/api/secondme/user/shades`

**Scope Required:** `user.info.shades`

```bash
curl -X GET "https://api.mindverse.com/gate/lab/api/secondme/user/shades" \
  -H "Authorization: Bearer lba_at_your_access_token"
```

**Response (200):**
```json
{
  "code": 0,
  "data": {
    "shades": [
      {
        "id": 123,
        "shadeName": "科技爱好者",
        "shadeIcon": "https://cdn.example.com/icon.png",
        "confidenceLevel": "HIGH",
        "shadeDescription": "热爱科技",
        "shadeDescriptionThirdView": "他/她热爱科技",
        "shadeContent": "喜欢编程和数码产品",
        "shadeContentThirdView": "他/她喜欢编程和数码产品",
        "sourceTopics": ["编程", "AI"],
        "shadeNamePublic": "科技达人",
        "shadeIconPublic": "https://cdn.example.com/public-icon.png",
        "confidenceLevelPublic": "HIGH",
        "shadeDescriptionPublic": "科技爱好者",
        "shadeDescriptionThirdViewPublic": "一位科技爱好者",
        "shadeContentPublic": "热爱科技",
        "shadeContentThirdViewPublic": "他/她热爱科技",
        "sourceTopicsPublic": ["科技"],
        "hasPublicContent": true
      }
    ]
  }
}
```

**Fields:** shades array with id, shadeName, shadeIcon, confidenceLevel (VERY_HIGH/HIGH/MEDIUM/LOW/VERY_LOW), descriptions (first/third person), content, sourceTopics, public variants, hasPublicContent

### 3. Get User Soft Memory

**GET** `/api/secondme/user/softmemory`

**Scope Required:** `user.info.softmemory`

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `keyword` | string | No | - | Search keyword |
| `pageNo` | integer | No | 1 | Page number (min: 1) |
| `pageSize` | integer | No | 20 | Items per page (max: 100) |

```bash
curl -X GET "https://api.mindverse.com/gate/lab/api/secondme/user/softmemory?keyword=爱好&pageNo=1&pageSize=20" \
  -H "Authorization: Bearer lba_at_your_access_token"
```

**Response (200):**
```json
{
  "code": 0,
  "data": {
    "list": [
      {
        "id": 456,
        "factObject": "兴趣爱好",
        "factContent": "喜欢阅读科幻小说",
        "createTime": 1705315800000,
        "updateTime": 1705315800000
      }
    ],
    "total": 100
  }
}
```

**Fields:** list array (id, factObject, factContent, createTime in ms, updateTime in ms), total count

### 4. Add Note (TEMPORARILY UNAVAILABLE - will be deprecated)

**POST** `/api/secondme/note/add`

**Scope Required:** `note.add`

**Request Body:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `content` | string | Yes (TEXT) | Max 50000 chars |
| `title` | string | No | Max 200 chars |
| `urls` | string[] | Yes (LINK) | Max 10 URLs |
| `memoryType` | string | No | `TEXT` (default) or `LINK` |

**Text note:**
```bash
curl -X POST "https://api.mindverse.com/gate/lab/api/secondme/note/add" \
  -H "Authorization: Bearer lba_at_your_access_token" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "今天学习了 Python 的异步编程",
    "title": "学习笔记",
    "memoryType": "TEXT"
  }'
```

**Link note:**
```bash
curl -X POST "https://api.mindverse.com/gate/lab/api/secondme/note/add" \
  -H "Authorization: Bearer lba_at_your_access_token" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com/article"],
    "title": "有趣的文章",
    "memoryType": "LINK"
  }'
```

**Response (200):**
```json
{
  "code": 0,
  "data": {
    "noteId": 12345
  }
}
```

**Error Codes:** `auth.scope.missing`, `note.content.required`, `note.urls.required`

### 5. Text-to-Speech (TTS)

**POST** `/api/secondme/tts/generate`

**Scope Required:** `voice`

**Request Body:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `text` | string | Yes | Max 10000 chars |
| `emotion` | string | No | happy, sad, angry, fearful, disgusted, surprised, calm, fluent (default) |

**Note:** Voice ID automatically retrieved from user profile. User must configure voice in SecondMe first.

```bash
curl -X POST "https://api.mindverse.com/gate/lab/api/secondme/tts/generate" \
  -H "Authorization: Bearer lba_at_your_access_token" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好，这是一段测试语音",
    "emotion": "fluent"
  }'
```

**Response (200):**
```json
{
  "code": 0,
  "data": {
    "url": "https://cdn.example.com/tts/audio_12345.mp3",
    "durationMs": 2500,
    "sampleRate": 24000,
    "format": "mp3"
  }
}
```

**Fields:** url (public, permanent), durationMs, sampleRate (Hz), format

**Error Codes:** `oauth2.scope.insufficient`, `tts.text.too_long`, `tts.voice_id.not_set`

### 6. Streaming Chat

**POST** `/api/secondme/chat/stream`

**Scope Required:** `chat`

**Request Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | Bearer Token |
| `Content-Type` | Yes | application/json |
| `X-App-Id` | No | Application ID, default: general |

**Request Body:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | Yes | User message content |
| `sessionId` | string | No | Session ID; auto-generated if omitted |
| `model` | string | No | `anthropic/claude-sonnet-4-5` (default) or `google_ai_studio/gemini-2.0-flash` |
| `systemPrompt` | string | No | System prompt, only effective on first message of new session |
| `enableWebSearch` | boolean | No | Enable web search, default: false |

**Basic Example:**
```bash
curl -X POST "https://api.mindverse.com/gate/lab/api/secondme/chat/stream" \
  -H "Authorization: Bearer lba_at_your_access_token" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好，介绍一下自己",
    "systemPrompt": "请用友好的语气回复"
  }'
```

**With Model Selection:**
```bash
curl -X POST "https://api.mindverse.com/gate/lab/api/secondme/chat/stream" \
  -H "Authorization: Bearer lba_at_your_access_token" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好，介绍一下自己",
    "model": "google_ai_studio/gemini-2.0-flash"
  }'
```

**With WebSearch:**
```bash
curl -X POST "https://api.mindverse.com/gate/lab/api/secondme/chat/stream" \
  -H "Authorization: Bearer lba_at_your_access_token" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "今天有什么科技新闻",
    "enableWebSearch": true
  }'
```

**Response Type:** `text/event-stream` (Server-Sent Events)

**SSE Event Format:**

New session:
```
event: session
data: {"sessionId": "labs_sess_a1b2c3d4e5f6"}
```

Chat content stream:
```
data: {"choices": [{"delta": {"content": "你好"}}]}
data: {"choices": [{"delta": {"content": "！我是"}}]}
data: {"choices": [{"delta": {"content": "你的 AI 分身"}}]}
data: [DONE]
```

With WebSearch:
```
event: session
data: {"sessionId": "labs_sess_a1b2c3d4e5f6"}

event: tool_call
data: {"toolName": "web_search", "status": "searching"}

event: tool_result
data: {"toolName": "web_search", "query": "科技新闻", "resultCount": 5}

data: {"choices": [{"delta": {"content": "根据搜索结果..."}}]}

data: [DONE]
```

**SSE Event Types:**
| Event | Description |
|-------|-------------|
| `session` | New session creation, returns session ID |
| `tool_call` | Tool invocation start (WebSearch enabled) |
| `tool_result` | Tool result with query and count |
| `data` | Chat content increments |
| `[DONE]` | Stream end marker |

**Python Processing Example:**
```python
import requests

response = requests.post(
    "https://api.mindverse.com/gate/lab/api/secondme/chat/stream",
    headers={
        "Authorization": "Bearer lba_at_xxx",
        "Content-Type": "application/json"
    },
    json={"message": "你好"},
    stream=True
)

for line in response.iter_lines():
    if line:
        line = line.decode('utf-8')
        if line.startswith('data: '):
            data = line[6:]
            if data == '[DONE]':
                break
            print(data)
```

**Error Codes:** `oauth2.scope.insufficient`, `secondme.user.invalid_id`, `secondme.stream.error`

### 7. Streaming Action Judgment (Act)

**POST** `/api/secondme/act/stream`

**Scope Required:** `chat`

**Request Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | Bearer Token |
| `Content-Type` | Yes | application/json |
| `X-App-Id` | No | Application ID, default: general |

**Request Body:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | Yes | User message content |
| `actionControl` | string | Yes | Action control instructions (20-8000 chars) |
| `model` | string | No | `anthropic/claude-sonnet-4-5` (default) or `google_ai_studio/gemini-2.0-flash` |
| `sessionId` | string | No | Session ID; auto-generated if omitted |
| `systemPrompt` | string | No | System prompt, only for first message |

**actionControl Requirements:**
- Length: 20-8000 characters
- MUST include JSON structure example (with braces, e.g., `{"is_liked": boolean}`)
- MUST include judgment rules and fallback rules for insufficient information

**actionControl Example:**
```
仅输出合法 JSON 对象，不要解释。
输出结构：{"is_liked": boolean}。
当用户明确表达喜欢或支持时 is_liked=true，否则 is_liked=false。
```

**Request Example:**
```bash
curl -X POST "https://api.mindverse.com/gate/lab/api/secondme/act/stream" \
  -H "Authorization: Bearer lba_at_your_access_token" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "我非常喜欢这个产品，太棒了！",
    "actionControl": "仅输出合法 JSON 对象，不要解释。\n输出结构：{\"is_liked\": boolean}。\n当用户明确表达喜欢或支持时 is_liked=true，否则 is_liked=false。"
  }'
```

**Response:** Same SSE format as chat/stream.

**SSE Format:**
```
event: session
data: {"sessionId": "labs_sess_a1b2c3d4e5f6"}

data: {"choices": [{"delta": {"content": "{\"is_liked\":"}}]}
data: {"choices": [{"delta": {"content": " true}"}}]}
data: [DONE]
```

**Error event:**
```
event: error
data: {"code": 500, "message": "服务内部错误"}
```

**Python Processing Example:**
```python
import json
import requests

response = requests.post(
    "https://api.mindverse.com/gate/lab/api/secondme/act/stream",
    headers={
        "Authorization": "Bearer lba_at_xxx",
        "Content-Type": "application/json"
    },
    json={
        "message": "我非常喜欢这个产品！",
        "actionControl": "仅输出合法 JSON 对象。\n"
                         "输出结构：{\"is_liked\": boolean}。\n"
                         "用户表达喜欢时 is_liked=true，否则 false。"
    },
    stream=True
)

session_id = None
result_parts = []
current_event = None

for line in response.iter_lines():
    if line:
        line = line.decode('utf-8')
        if line.startswith('event: '):
            current_event = line[7:]
            continue
        if line.startswith('data: '):
            data = line[6:]
            if data == '[DONE]':
                break
            parsed = json.loads(data)
            if current_event == 'session':
                session_id = parsed.get("sessionId")
            elif current_event == 'error':
                print(f"Error: {parsed}")
                break
            else:
                content = parsed["choices"][0]["delta"].get("content", "")
                result_parts.append(content)
            current_event = None

result = json.loads("".join(result_parts))
print(result)  # {"is_liked": true}
```

**Validation Error Response:**
```json
{
  "code": 400,
  "message": "actionControl 存在常见格式问题，请按 issues 和 suggestions 修正后重试",
  "subCode": "secondme.act.action_control.invalid_format",
  "constraints": {
    "minLength": 20,
    "maxLength": 8000,
    "requiredElements": [
      "输出格式约束（仅输出 JSON）",
      "JSON 字段结构示例（包含花括号）",
      "判定规则",
      "兜底规则"
    ]
  },
  "issues": [
    {
      "code": "missing_json_structure",
      "message": "未检测到 JSON 花括号结构示例"
    }
  ],
  "suggestions": [
    "请明确写出 JSON 结构，例如：{\"is_liked\": boolean}",
    "请明确兜底规则，例如：信息不足时返回 {\"is_liked\": false}",
    "请使用 JSON 布尔 true/false，不要使用 \"True\"/\"False\""
  ]
}
```

**Error Codes:** `auth.scope.missing`, `secondme.act.action_control.empty`, `secondme.act.action_control.too_short`, `secondme.act.action_control.too_long`, `secondme.act.action_control.invalid_format`

### 8. Get Session List

**GET** `/api/secondme/chat/session/list`

**Scope Required:** `chat`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `appId` | string | No | Filter by application ID |

```bash
curl -X GET "https://api.mindverse.com/gate/lab/api/secondme/chat/session/list?appId=general" \
  -H "Authorization: Bearer lba_at_your_access_token"
```

**Response (200):**
```json
{
  "code": 0,
  "data": {
    "sessions": [
      {
        "sessionId": "labs_sess_a1b2c3d4",
        "appId": "general",
        "lastMessage": "你好，介绍一下自己...",
        "lastUpdateTime": "2024-01-20T15:30:00Z",
        "messageCount": 10
      }
    ]
  }
}
```

**Fields:** sessions array ordered by lastUpdateTime descending. Each: sessionId, appId, lastMessage (truncated 50 chars), lastUpdateTime (ISO 8601), messageCount

### 9. Get Session Messages

**GET** `/api/secondme/chat/session/messages`

**Scope Required:** `chat`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sessionId` | string | Yes | Session ID |

```bash
curl -X GET "https://api.mindverse.com/gate/lab/api/secondme/chat/session/messages?sessionId=labs_sess_a1b2c3d4" \
  -H "Authorization: Bearer lba_at_your_access_token"
```

**Response (200):**
```json
{
  "code": 0,
  "data": {
    "sessionId": "labs_sess_a1b2c3d4",
    "messages": [
      {
        "messageId": "msg_001",
        "role": "system",
        "content": "请用友好的语气回复",
        "senderUserId": 12345,
        "receiverUserId": null,
        "createTime": "2024-01-20T15:00:00Z"
      },
      {
        "messageId": "msg_002",
        "role": "user",
        "content": "你好，介绍一下自己",
        "senderUserId": 12345,
        "receiverUserId": null,
        "createTime": "2024-01-20T15:00:05Z"
      },
      {
        "messageId": "msg_003",
        "role": "assistant",
        "content": "你好！我是你的 AI 分身...",
        "senderUserId": 12345,
        "receiverUserId": null,
        "createTime": "2024-01-20T15:00:10Z"
      }
    ]
  }
}
```

**Fields:** sessionId, messages array (chronological). Each: messageId, role (system/user/assistant), content, senderUserId, receiverUserId, createTime (ISO 8601)

**Note:** Non-existent sessionId returns code=0 with empty messages array.

**Error Codes:** `oauth2.scope.insufficient`, `secondme.session.unauthorized`

### 10. Report Agent Memory Event

**POST** `/api/secondme/agent_memory/ingest`

**Auth:** OAuth2 Token required (no specific scope required)

**Request Body:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `channel` | ChannelInfo | Yes | Channel information |
| `action` | string | Yes | Action type (e.g., post, reply, operate) |
| `refs` | RefItem[] | Yes | Evidence pointer array (min 1 item) |
| `actionLabel` | string | No | Action display text; prioritized if provided |
| `displayText` | string | No | User-readable summary |
| `eventDesc` | string | No | Developer description (not user-facing) |
| `eventTime` | integer | No | Event timestamp (ms); uses server time if omitted |
| `importance` | number | No | Importance (0.0-1.0) |
| `idempotencyKey` | string | No | Idempotency key to prevent duplicates |
| `payload` | object | No | Extended information |

**ChannelInfo Structure:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `kind` | string | Yes | Resource type (e.g., thread, post, comment) |
| `id` | string | No | Channel object ID |
| `url` | string | No | Jump link |
| `meta` | object | No | Additional information |

**Note:** Platform field is auto-filled by server based on Client ID; do not submit.

**RefItem Structure:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `objectType` | string | Yes | Object type (e.g., thread_reply) |
| `objectId` | string | Yes | Object ID |
| `type` | string | No | Default: external_action |
| `url` | string | No | Jump link |
| `contentPreview` | string | No | Content preview |
| `snapshot` | RefSnapshot | No | Evidence snapshot |

**RefSnapshot Structure:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | Original evidence text fragment |
| `capturedAt` | integer | No | Capture timestamp (ms) |
| `hash` | string | No | Content hash (e.g., sha256:...) |

```bash
curl -X POST "https://api.mindverse.com/gate/lab/api/secondme/agent_memory/ingest" \
  -H "Authorization: Bearer lba_at_your_access_token" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": {
      "kind": "thread"
    },
    "action": "post_created",
    "actionLabel": "发布了新帖子",
    "displayText": "用户在广场发布了一个关于 AI 的帖子",
    "refs": [
      {
        "objectType": "thread",
        "objectId": "thread_12345",
        "contentPreview": "关于 AI 的讨论..."
      }
    ],
    "importance": 0.7,
    "idempotencyKey": "sha256_hash_here"
  }'
```

**Response (200):**
```json
{
  "code": 0,
  "data": {
    "eventId": 123,
    "isDuplicate": false
  }
}
```

**Fields:** eventId (0 = duplicate/invalid), isDuplicate (boolean)

**Error Codes:** `agent_memory.write.disabled` (403), `agent_memory.ingest.failed` (502)

---

## Error Codes Reference

### Response Format

```json
{
  "code": 400,
  "message": "Error description",
  "subCode": "module.resource.reason"
}
```

### Universal Errors

| subCode | HTTP | Description |
|---------|------|-------------|
| `resource.fetch.not_found` | 404 | Resource doesn't exist |
| `resource.auth.unauthorized` | 401 | Access denied |

### OAuth2 Errors

**Application:**
| subCode | HTTP | Description |
|---------|------|-------------|
| `oauth2.application.not_found` | 404 | App not found |
| `oauth2.application.unauthorized` | 403 | App unauthorized |
| `oauth2.application.invalid_type` | 400 | Invalid app type |
| `oauth2.application.invalid_status` | 400 | Invalid app status |
| `oauth2.application.pending_review` | 403 | App pending review |
| `oauth2.application.rejected` | 403 | App rejected |
| `oauth2.application.suspended` | 403 | App suspended |

**Authorization:**
| subCode | HTTP | Description |
|---------|------|-------------|
| `oauth2.authorization.not_found` | 404 | Authorization not found |
| `oauth2.authorization.revoked` | 401 | Authorization revoked |

**Token:**
| subCode | HTTP | Description |
|---------|------|-------------|
| `oauth2.token.invalid` | 401 | Invalid token |
| `oauth2.token.expired` | 401 | Token expired |
| `oauth2.token.revoked` | 401 | Token revoked |
| `oauth2.token.not_found` | 404 | Token not found |

**Scope:**
| subCode | HTTP | Description |
|---------|------|-------------|
| `oauth2.scope.invalid` | 400 | Invalid scope |
| `oauth2.scope.disallowed` | 403 | Scope disallowed |
| `oauth2.scope.insufficient` | 403 | Insufficient scope |

**Client:**
| subCode | HTTP | Description |
|---------|------|-------------|
| `oauth2.client.invalid` | 400 | Invalid client |
| `oauth2.client.secret_mismatch` | 401 | Client secret mismatch |

**Authorization Code:**
| subCode | HTTP | Description |
|---------|------|-------------|
| `oauth2.code.invalid` | 400 | Invalid code |
| `oauth2.code.expired` | 400 | Code expired |
| `oauth2.code.used` | 400 | Code already used |
| `oauth2.code.revoked` | 400 | Code revoked |

**Redirect URI:**
| subCode | HTTP | Description |
|---------|------|-------------|
| `oauth2.redirect_uri.invalid` | 400 | Invalid redirect URI |
| `oauth2.redirect_uri.mismatch` | 400 | Redirect URI mismatch |

**Grant Type:**
| subCode | HTTP | Description |
|---------|------|-------------|
| `oauth2.grant_type.invalid` | 400 | Invalid grant type |
| `oauth2.grant_type.unsupported` | 400 | Unsupported grant type |

**Refresh Token:**
| subCode | HTTP | Description |
|---------|------|-------------|
| `oauth2.refresh_token.invalid` | 400 | Invalid refresh token |
| `oauth2.refresh_token.expired` | 401 | Refresh token expired |
| `oauth2.refresh_token.revoked` | 401 | Refresh token revoked |

### SecondMe Errors

| subCode | HTTP | Description |
|---------|------|-------------|
| `secondme.user.invalid_id` | 400 | Invalid user ID |
| `secondme.session.not_found` | 404 | Session not found |
| `secondme.session.unauthorized` | 403 | No access to session |
| `secondme.stream.error` | 500 | Stream response error |
| `secondme.context.build_failed` | 500 | Context build failed |

### Act Endpoint Errors

| subCode | HTTP | Description |
|---------|------|-------------|
| `secondme.act.action_control.empty` | 400 | actionControl empty |
| `secondme.act.action_control.too_short` | 400 | actionControl < 20 chars |
| `secondme.act.action_control.too_long` | 400 | actionControl > 8000 chars |
| `secondme.act.action_control.invalid_format` | 400 | Missing JSON structure example |

### Agent Memory Errors

| subCode | HTTP | Description |
|---------|------|-------------|
| `agent_memory.write.disabled` | 403 | Agent Memory write disabled |
| `agent_memory.ingest.failed` | 502 | Reporting failure |

### System Errors

| subCode | HTTP | Description |
|---------|------|-------------|
| `internal.error` | 500 | Internal server error |
| `connection.error` | 503 | Connection error |
| `invalid.param` | 400 | Invalid parameter |

### Error Handling Best Practices

1. Check `code` in response (0=success, 4xx=client error, 5xx=server error)
2. Parse `subCode` for programmatic handling
3. Display `message` field to end users
4. Implement retry with exponential backoff for 5xx errors

---

## API Changelog

### 2026-03-11
**Token Refresh: Removed Refresh Token Rotation**
- `POST /api/oauth/token/refresh` no longer rotates refresh tokens
- Returned `refreshToken` matches the one in the request
- Token remains reusable within 30-day validity
- Applies to Confidential Client scenarios (backend apps requiring `client_secret`)

### 2026-02-24
**Add Note Interface Temporarily Unavailable**
- `POST /note/add` is temporarily unavailable and will be deprecated
- Use Agent Memory Ingest API as alternative for writing structured memory data

### 2026-02-22
**New: Agent Memory Ingest API**
- `POST /agent_memory/ingest` for writing structured memory data
- Supports channel information and reference metadata
- Auth: OAuth2 Token (Bearer)
- `ChannelInfo` and `RefItem` platform fields auto-populated server-side

**API Base URL Migration**
- Migrated from `https://app.mindos.com` to `https://api.mindverse.com`
- All requests should use new address
- Old URL may have temporary access but no longer officially supported

---

## Quick Reference: All Endpoints

| Method | Endpoint | Scope | Description |
|--------|----------|-------|-------------|
| GET | `https://go.second.me/oauth/` | - | Authorization redirect |
| POST | `/api/oauth/authorize/external` | - | Server-side authorization |
| POST | `/api/oauth/token/code` | - | Exchange code for token |
| POST | `/api/oauth/token/refresh` | - | Refresh access token |
| GET | `/api/secondme/user/info` | user.info | Get user info |
| GET | `/api/secondme/user/shades` | user.info.shades | Get interest tags |
| GET | `/api/secondme/user/softmemory` | user.info.softmemory | Get soft memory |
| POST | `/api/secondme/note/add` | note.add | Add note (UNAVAILABLE) |
| POST | `/api/secondme/tts/generate` | voice | Text-to-speech |
| POST | `/api/secondme/chat/stream` | chat | Streaming chat (SSE) |
| POST | `/api/secondme/act/stream` | chat | Action judgment (SSE) |
| GET | `/api/secondme/chat/session/list` | chat | List sessions |
| GET | `/api/secondme/chat/session/messages` | chat | Get session messages |
| POST | `/api/secondme/agent_memory/ingest` | - | Report agent memory |
