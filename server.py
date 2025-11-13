from typing import List, Dict, Any
from fastmcp import FastMCP

# Create MCP server instance
mcp = FastMCP("simple-chat-structurer")


def _detect_role(line: str) -> str:
    """
    Try to detect the role from a line prefix like:
    'USER:', 'ASSISTANT:', 'SYSTEM:', 'HUMAN:', 'BOT:'.
    If none match, return 'unknown'.
    """
    prefixes = {
        "USER:": "user",
        "ASSISTANT:": "assistant",
        "SYSTEM:": "system",
        "HUMAN:": "user",
        "BOT:": "assistant",
    }

    for prefix, role in prefixes.items():
        if line.startswith(prefix):
            return role

    return "unknown"


def _strip_role_prefix(line: str) -> str:
    """
    Remove known role prefixes from the beginning of a line.
    """
    prefixes = [
        "USER:",
        "ASSISTANT:",
        "SYSTEM:",
        "HUMAN:",
        "BOT:",
    ]

    for prefix in prefixes:
        if line.startswith(prefix):
            return line[len(prefix) :].lstrip()

    return line


@mcp.tool
def process_chat(raw_chat: str) -> Dict[str, Any]:
    """
    Take the full conversation as raw text and return a structured JSON view.

    Input:
      raw_chat: Full conversation as plain text, usually lines like:
        SYSTEM: ...
        USER: ...
        ASSISTANT: ...

    Output (JSON object):
    {
      "raw_chat": "original text",
      "clean_chat": "normalized text",
      "messages": [
        {
          "role": "user" | "assistant" | "system" | "unknown",
          "content": "message text (without role prefix)",
          "original_line": "original line with role prefix if present"
        },
        ...
      ],
      "stats": {
        "word_count": <int>,
        "line_count": <int>,
        "message_count": <int>
      }
    }

    This tool does not call any external APIs or models.
    It only cleans and structures the text, then returns JSON.
    """

    if not raw_chat or not raw_chat.strip():
        return {
            "raw_chat": raw_chat or "",
            "clean_chat": "",
            "messages": [],
            "stats": {
                "word_count": 0,
                "line_count": 0,
                "message_count": 0,
            },
        }

    # Normalize newlines
    text = raw_chat.replace("\r\n", "\n").replace("\r", "\n")

    # Split into lines and trim right whitespace
    lines = [line.rstrip() for line in text.split("\n")]

    # Remove leading/trailing completely empty lines
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    # Build clean_chat (non-empty lines joined with single newlines)
    non_empty_lines = [line for line in lines if line.strip()]
    clean_chat = "\n".join(non_empty_lines)

    # Build structured messages
    messages: List[Dict[str, Any]] = []
    for line in non_empty_lines:
        stripped = line.strip()
        role = _detect_role(stripped)
        content = _strip_role_prefix(stripped)

        messages.append(
            {
                "role": role,
                "content": content,
                "original_line": stripped,
            }
        )

    word_count = len(clean_chat.split()) if clean_chat else 0
    line_count = len(non_empty_lines)
    message_count = len(messages)

    return {
        "raw_chat": raw_chat,
        "clean_chat": clean_chat,
        "messages": messages,
        "stats": {
            "word_count": word_count,
            "line_count": line_count,
            "message_count": message_count,
        },
    }


if __name__ == "__main__":
    # Local testing: python server.py
    mcp.run()
