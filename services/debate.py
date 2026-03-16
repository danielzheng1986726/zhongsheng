"""Debate script generation — the core orchestrator.

Takes a topic and generates a full courtroom debate script
in the SCRIPT DSL format that the frontend engine can play.
"""

import json
from services import llm, secondme, zhihu

FACTION_PROMPT = """你是一个社会议题分析专家。分析以下讨论话题，识别出 4 个不同的观点阵营。

话题：「{topic}」
{context}

输出严格 JSON，不要任何解释文字：
{{
  "factions": [
    {{
      "id": "faction_1",
      "name": "2-4字阵营名",
      "emoji": "一个emoji",
      "color": "#十六进制颜色",
      "title": "「4-8字口号」",
      "catchphrase": "3-5个标签 · 用顿号分隔",
      "position": "30字以内核心立场"
    }}
  ]
}}

颜色建议：第1个用 #e8785a，第2个用 #5a9ae8，第3个用 #a078e0，第4个用 #50c0a0。
每个阵营要有鲜明对比，名字要犀利有梗。"""

SCRIPT_PROMPT = """你是「众声法庭」的编剧。根据以下阵营信息，生成一场法庭辩论剧本。

话题：「{topic}」

阵营信息：
{factions_json}

## 剧本格式规则

输出一个 JSON 对象，包含 script 数组和结果数据。每个 script 元素是以下类型之一：

1. {{"type": "narrate", "speaker": "kanshan", "text": "审判长台词"}}
2. {{"type": "vs", "left": "faction_id", "right": "faction_id"}}
3. {{"type": "say", "side": "left"|"right", "char": "faction_id", "expr": "default"|"angry"|"shock"|"think"|"point"|"moved", "text": "角色台词", "effect": "none"|"anger"|"sweat"|"spark"}}
4. {{"type": "objection", "text": "異議あり！"|"等一下！"|"共識達成！", "style": "default"|"holdit"|"consensus"}}
5. {{"type": "consensus"}}

## 剧情要求

- 开头：审判长介绍案件（1-2步 narrate）
- 第一轮：faction_1 vs faction_2 对峙（vs + 4-6步 say 交替）
- 转折：objection（holdit 风格）
- 第二轮：faction_3 vs faction_4 对峙（vs + 4-6步 say 交替）
- 高潮：objection（default 風格，異議あり！）
- 真相揭示：审判长总结（2-3步 narrate，用 think 和 moved 表情）
- 共识达成：objection（consensus 风格）+ consensus 步骤
- 总共 25-35 步
- 语言风格：辛辣幽默，网络梗，但最终温暖
- 台词要短（每句 15-40 字），像真实辩论那样尖锐

## 结果数据

同时输出 consensus_items（3个共识）、golden_quote（金句）、warmth_message（温暖总结）。

输出严格 JSON：
{{
  "script": [...],
  "consensus_items": [
    {{"pct": "XX%", "label": "共识描述（10字内）", "detail": "一句话解释"}},
    {{"pct": "XX%", "label": "共识描述", "detail": "一句话解释"}},
    {{"pct": "XX%", "label": "共识描述", "detail": "一句话解释"}}
  ],
  "golden_quote": "一句有力的金句",
  "warmth_message": "3行温暖总结，可用 <em> 标签强调关键词"
}}"""


def _build_chars(factions: list) -> dict:
    """Build CHARS object from faction data."""
    chars = {
        "kanshan": {
            "name": "刘看山",
            "cls": "char-kanshan",
            "color": "#4ecde6",
            "emoji": "🐻‍❄️",
            "title": "「审判长」",
            "catchphrase": "公正 · 冷静 · 真相",
            "angry_emoji": "💢",
            "shock_emoji": "❗",
            "think_emoji": "🤔",
            "moved_emoji": "💛",
            "point_emoji": "👆",
        }
    }
    emoji_sets = [
        {"angry": "💢", "shock": "💧", "think": "🤔", "moved": "💛", "point": "👆"},
        {"angry": "💢", "shock": "😱", "think": "🧐", "moved": "❤️", "point": "☝️"},
        {"angry": "🔥", "shock": "😨", "think": "💭", "moved": "🥹", "point": "👉"},
        {"angry": "⚡", "shock": "😳", "think": "🫤", "moved": "🤝", "point": "✋"},
    ]
    for i, f in enumerate(factions):
        eset = emoji_sets[i % len(emoji_sets)]
        chars[f["id"]] = {
            "name": f["name"],
            "cls": f"char-dynamic-{i}",
            "color": f["color"],
            "emoji": f["emoji"],
            "title": f["title"],
            "catchphrase": f["catchphrase"],
            "angry_emoji": eset["angry"],
            "shock_emoji": eset["shock"],
            "think_emoji": eset["think"],
            "moved_emoji": eset["moved"],
            "point_emoji": eset["point"],
        }
    return chars


async def generate(
    topic: str,
    access_token: str | None = None,
):
    """Generate a full debate. Yields SSE-style progress events.

    Final event has type='done' with the complete payload.
    """
    context = ""

    # Step 1: Try to fetch context from Zhihu
    yield {"phase": "fetching", "message": "正在获取讨论数据..."}
    try:
        results = await zhihu.search(topic, count=5)
        if results:
            snippets = []
            for r in results[:5]:
                title = r.get("title", "")
                excerpt = r.get("content_text", r.get("content", ""))[:200]
                if title or excerpt:
                    snippets.append(f"- {title}: {excerpt}")
            if snippets:
                context = "知乎讨论摘要：\n" + "\n".join(snippets)
    except Exception:
        pass

    # Step 2: Analyze factions
    yield {"phase": "analyzing", "message": "AI 正在分析观点阵营..."}
    faction_messages = [
        {"role": "user", "content": FACTION_PROMPT.format(topic=topic, context=context)}
    ]
    try:
        faction_data = await llm.chat_json(faction_messages, temperature=0.5)
        factions = faction_data["factions"][:4]  # Max 4 factions
    except Exception:
        # Fallback factions
        factions = [
            {"id": "faction_1", "name": "支持派", "emoji": "✊", "color": "#e8785a",
             "title": "「坚定支持」", "catchphrase": "理想 · 坚持 · 前行", "position": "坚定支持这个方向"},
            {"id": "faction_2", "name": "反对派", "emoji": "🚫", "color": "#5a9ae8",
             "title": "「理性反对」", "catchphrase": "冷静 · 质疑 · 反思", "position": "需要重新考虑"},
            {"id": "faction_3", "name": "中间派", "emoji": "⚖️", "color": "#a078e0",
             "title": "「两边都有理」", "catchphrase": "平衡 · 兼容 · 折中", "position": "各有道理要综合看"},
            {"id": "faction_4", "name": "实用派", "emoji": "🎯", "color": "#50c0a0",
             "title": "「看情况」", "catchphrase": "务实 · 灵活 · 因地制宜", "position": "具体问题具体分析"},
        ]

    chars = _build_chars(factions)
    faction_names = [f["name"] for f in factions]
    yield {
        "phase": "factions",
        "message": f"识别到 {len(factions)} 个观点阵营：{' / '.join(faction_names)}",
        "factions": factions,
    }

    # Step 3: Generate debate script
    yield {"phase": "scripting", "message": "生成法庭辩论剧本..."}
    script_messages = [
        {
            "role": "user",
            "content": SCRIPT_PROMPT.format(
                topic=topic,
                factions_json=json.dumps(factions, ensure_ascii=False, indent=2),
            ),
        }
    ]
    try:
        result = await llm.chat_json(script_messages, model="deepseek", temperature=0.7, max_tokens=8192)
        script = result["script"]
        consensus_items = result.get("consensus_items", [])
        golden_quote = result.get("golden_quote", "")
        warmth_message = result.get("warmth_message", "")
    except Exception as e:
        # Minimal fallback script
        f1, f2 = factions[0]["id"], factions[1]["id"]
        script = [
            {"type": "narrate", "speaker": "kanshan", "text": f"今日案件：「{topic}」——开庭！"},
            {"type": "vs", "left": f1, "right": f2},
            {"type": "say", "side": "left", "char": f1, "expr": "default", "text": factions[0]["position"], "effect": "none"},
            {"type": "say", "side": "right", "char": f2, "expr": "angry", "text": factions[1]["position"], "effect": "anger"},
            {"type": "objection", "text": "共識達成！", "style": "consensus"},
            {"type": "consensus"},
        ]
        consensus_items = [{"pct": "80%", "label": "殊途同归", "detail": "大家的出发点其实一样"}]
        golden_quote = "吵来吵去，其实我们都想好好生活。"
        warmth_message = f"关于「{topic}」的讨论<em>远没有看起来那么分裂</em>。"

    # Step 4: Second Me participation (if logged in)
    user_char = None
    if access_token:
        yield {"phase": "secondme", "message": "读取你的 Second Me 认知画像..."}
        try:
            shades = await secondme.get_user_shades(access_token)
            shade_tags = [s.get("shadeName", "") for s in shades[:5]]

            # Ask Second Me to comment on the debate
            debate_summary = "\n".join(
                [f"- {f['name']}：{f['position']}" for f in factions]
            )
            sm_prompt = (
                f"你是用户在「众声法庭」中的代表。讨论话题是「{topic}」。\n"
                f"以下是各阵营观点：\n{debate_summary}\n"
                f"用户的兴趣标签：{', '.join(shade_tags)}\n"
                f"请以用户的口吻，用 2-3 句话表达你对这个话题的真实看法。要有个性，真诚，不超过60字。"
            )
            sm_response = await secondme.chat_full(access_token, sm_prompt)

            if sm_response:
                user_info = await secondme.get_user_info(access_token)
                user_name = user_info.get("name", "我的分身")
                user_char = {
                    "id": "user_avatar",
                    "name": user_name,
                    "emoji": "🧑‍💻",
                    "color": "#f0c050",
                    "title": "「特殊证人」",
                    "catchphrase": " · ".join(shade_tags[:3]) if shade_tags else "我的观点",
                }
                chars["user_avatar"] = {
                    **user_char,
                    "cls": "char-user",
                    "angry_emoji": "💢",
                    "shock_emoji": "😲",
                    "think_emoji": "🤔",
                    "moved_emoji": "💛",
                    "point_emoji": "👆",
                }
                # Insert user avatar segment before consensus
                insert_idx = len(script) - 1
                for i, step in enumerate(script):
                    if step.get("type") == "consensus":
                        insert_idx = i
                        break
                user_steps = [
                    {"type": "narrate", "speaker": "kanshan", "text": f"法庭传召特殊证人——{user_name}的 AI 分身。"},
                    {"type": "say", "side": "left", "char": "user_avatar", "expr": "think", "text": sm_response, "effect": "spark"},
                ]
                script = script[:insert_idx] + user_steps + script[insert_idx:]
        except Exception:
            pass

    yield {"phase": "ready", "message": "准备开庭！"}

    # Final payload
    yield {
        "phase": "done",
        "script": script,
        "chars": chars,
        "consensus_items": consensus_items,
        "golden_quote": golden_quote,
        "warmth_message": warmth_message,
        "topic": topic,
        "user_char": user_char,
    }
