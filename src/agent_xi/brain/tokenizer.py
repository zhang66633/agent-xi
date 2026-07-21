"""Token 计数器 — 启发式估算。

不依赖特定 tokenizer 库（DeepSeek/Claude 各有自己的分词器），
采用保守估算确保不超出模型上下文窗口。

估算规则：
- 中文字符：~1.5 token/字
- 英文单词：~1.3 token/word（含标点）
- JSON/代码：~0.3 token/char（结构化文本压缩率高）
- 安全系数：最终结果 × 1.1（宁多估不少估）
"""

from __future__ import annotations

import re

from ..llm.types import Message, ToolDefinition

# 安全系数（宁可少放消息，不要超出窗口）
_SAFETY_FACTOR = 1.1

# 每条消息的固定开销（role 标记、分隔符等）
_PER_MESSAGE_OVERHEAD = 4


def _count_text_tokens(text: str) -> int:
    """估算纯文本的 token 数。

    策略：区分中文字符和非中文文本分别计算。
    """
    if not text:
        return 0

    # 中文字符数（含中文标点）
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", text))

    # 非中文部分：按空格分词估算
    non_chinese = re.sub(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", " ", text)
    words = len(non_chinese.split())

    # 中文 ~1.5 token/字，英文 ~1.3 token/word
    raw = chinese_chars * 1.5 + words * 1.3

    return int(raw * _SAFETY_FACTOR) + 1


def count_message_tokens(message: Message) -> int:
    """估算单条消息的 token 数。"""
    if isinstance(message.content, str):
        text_tokens = _count_text_tokens(message.content)
    else:
        # 内容块列表
        text_tokens = 0
        for block in message.content:
            if hasattr(block, "text"):
                text_tokens += _count_text_tokens(block.text)
            elif hasattr(block, "content"):
                text_tokens += _count_text_tokens(block.content)
            elif hasattr(block, "arguments"):
                # ToolUseBlock: 估算参数 JSON
                import json

                args_str = json.dumps(block.arguments, ensure_ascii=False)
                text_tokens += _count_text_tokens(args_str)
                text_tokens += _count_text_tokens(block.name)

    return text_tokens + _PER_MESSAGE_OVERHEAD


def count_messages_tokens(messages: list[Message]) -> int:
    """估算消息列表的总 token 数。"""
    return sum(count_message_tokens(m) for m in messages)


def count_tools_tokens(tools: list[ToolDefinition]) -> int:
    """估算工具定义列表的 token 数（JSON schema 文本）。"""
    if not tools:
        return 0
    import json

    total_text = ""
    for tool in tools:
        total_text += tool.name + tool.description
        total_text += json.dumps(tool.to_json_schema(), ensure_ascii=False)
    return _count_text_tokens(total_text)


class TokenCounter:
    """Token 计数器（有状态，可缓存）。"""

    def count_text(self, text: str) -> int:
        """估算文本 token 数。"""
        return _count_text_tokens(text)

    def count_message(self, message: Message) -> int:
        """估算单条消息 token 数。"""
        return count_message_tokens(message)

    def count_messages(self, messages: list[Message]) -> int:
        """估算消息列表总 token 数。"""
        return count_messages_tokens(messages)

    def count_tools(self, tools: list[ToolDefinition]) -> int:
        """估算工具定义 token 数。"""
        return count_tools_tokens(tools)
