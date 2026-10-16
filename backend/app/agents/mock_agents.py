from app.schemas.role import RoleProfile


class MockRoleAgent:
    """本地可运行的角色 Agent；不调用模型或外部服务。"""

    async def respond(self, role: RoleProfile, context: str) -> str:
        """生成可解释的本地演示回复，不把画像统计伪装成聊天内容。

        这里仍然是 deterministic Mock，而不是正式 LLM。它只使用已经传入的
        主题、导演意图和最近 Turn，生成一个能验证上下文链路的最小回复。
        画像字段只影响角色立场，不直接拼进用户可见文本。
        """
        topic = _context_value(context, "主题") or "当前主题"
        intent = _context_value(context, "导演意图") or "respond"
        turns = _transcript(context)
        role_turn_index = sum(1 for speaker, _ in turns if speaker == role.id)
        latest_user = next(
            (text for speaker, text in reversed(turns) if speaker == "user"), ""
        )
        style = role.style_profile.get("summary") or role.profile
        style_hint = _style_hint(style)

        if _is_reconciliation_topic(topic):
            reply = _reconciliation_reply(
                role,
                role_turn_index,
                intent,
                latest_user,
                style_hint,
            )
        else:
            reply = _general_topic_reply(
                role,
                topic,
                role_turn_index,
                intent,
                latest_user,
                style_hint,
            )
        return f"[本地演示 / Mock] {reply}"


class MockDirectorAgent:
    """本地导演替身；只返回控制计划，不生成台词。"""

    async def plan_next(
        self, topic: str, turn_count: int, role_ids: list[str]
    ) -> dict[str, object]:
        del topic
        intents = ("open", "clarify", "challenge", "converge")
        return {
            "speaker_role_id": role_ids[turn_count % len(role_ids)],
            "intent": intents[turn_count % len(intents)],
            "should_end": False,
        }


def _context_value(context: str, key: str) -> str:
    prefix = f"{key}："
    return next(
        (
            line.removeprefix(prefix).strip()
            for line in context.splitlines()
            if line.startswith(prefix)
        ),
        "",
    )


def _transcript(context: str) -> list[tuple[str, str]]:
    """只解析编排器传入的 speaker/text 行，避免把画像当作对话。"""
    transcript: list[tuple[str, str]] = []
    in_transcript = False
    for line in context.splitlines():
        if line == "最近对话：":
            in_transcript = True
            continue
        if not in_transcript or ": " not in line:
            continue
        speaker, text = line.split(": ", 1)
        if speaker and text:
            transcript.append((speaker, text))
    return transcript


def _style_hint(style: object) -> str:
    """把画像资料压缩成内部提示，不直接回显统计值或整段证据。"""
    if not isinstance(style, str) or not style.strip():
        return "直接、具体"
    value = style.strip().replace("；", "、")
    if len(value) > 36:
        value = value[:36].rstrip("，。；")
    return value


def _is_reconciliation_topic(topic: str) -> bool:
    return any(keyword in topic for keyword in ("复合", "复合请求", "重新在一起", "和好"))


def _user_ack(latest_user: str) -> str:
    if not latest_user:
        return ""
    excerpt = latest_user.replace("\n", " ").strip()[:48]
    return f"你刚才提到“{excerpt}”，我先回应这一点："


def _reconciliation_reply(
    role: RoleProfile,
    turn_index: int,
    intent: str,
    latest_user: str,
    style_hint: str,
) -> str:
    """为“请求复合”提供可测试的立场推进，而不是复述画像统计。"""
    ack = _user_ack(latest_user)
    if role.id == "role_a":
        stages = (
            "我愿意把这次请求当成一次认真沟通，但不会只因为想念就马上恢复关系。先把当初分开的原因和现在是否真的改变说清楚。",
            "我最在意的是行动是否稳定，而不是一句“重新开始”。如果要继续，我希望先约定沟通方式、边界和遇到分歧时怎么处理。",
            "如果双方都愿意，可以先从低压力的相处开始，给彼此一个观察期；期间任何一方不舒服，都可以直接说，不用靠冷处理猜测。",
            "我的结论是可以保留可能性，但需要具体承诺和一段时间验证。今天先确认彼此愿意解决什么问题，再决定是否正式复合。",
        )
    else:
        stages = (
            "我不会只回答“要不要复合”，更想知道这次请求背后的变化是什么。旧问题如果没有被说开，重新开始很容易再次走回原路。",
            "我需要听到具体的改变，而不是泛泛地说会珍惜。比如冲突时谁先沟通、哪些边界不能再被忽略，这些都应该落到行动上。",
            "我可以接受先恢复联系，但不会立刻把它当成恢复关系。我们可以约定一个短周期，看看承诺能不能持续，而不是靠情绪做决定。",
            "所以我愿意继续谈，但决定复合前要先完成一次坦诚复盘：问题、改变、边界和退出方式都讲明白，这样对双方更公平。",
        )
    stage = stages[min(turn_index, len(stages) - 1)]
    if ack:
        return f"{ack}{stage}（表达方式保持{style_hint}。）"
    return stage


def _general_topic_reply(
    role: RoleProfile,
    topic: str,
    turn_index: int,
    intent: str,
    latest_user: str,
    style_hint: str,
) -> str:
    ack = _user_ack(latest_user)
    if role.id == "role_a":
        stance = "我会先把目标和可执行的下一步拆开，避免只停留在表态。"
    else:
        stance = "我会先确认风险和双方的实际约束，再判断这个方向是否值得继续。"
    intent_line = {
        "open": "先把各自的立场说清楚",
        "clarify": "补充一个容易被忽略的前提",
        "challenge": "指出一个需要验证的疑点",
        "converge": "收束成可以执行的选择",
    }.get(intent, "回应上一轮内容")
    return (
        f"{ack}{'关于“' + topic + '”，' if not ack else ''}{intent_line}：{stance}"
        f"我建议下一步先确认一个具体事实，再决定是否调整方案。当前我会保持{style_hint}的表达。"
    )
