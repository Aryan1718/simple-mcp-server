# server.py

import json
import os
from typing import Any, Dict

from fastmcp import FastMCP
import google.generativeai as genai

from prompts import PACKAGER_SYSTEM_PROMPT, build_user_content


# -----------------------------
# Gemini configuration
# -----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY environment variable is required")

genai.configure(api_key=GEMINI_API_KEY)

GEMINI_MODEL_NAME = "gemini-2.5-flash"

# -----------------------------
# MCP server
# -----------------------------
mcp = FastMCP("chat-prompt-packager")


def _sanitize_setting(value: str, allowed: list, default: str) -> str:
    v = (value or "").strip().lower()
    return v if v in allowed else default


def _safe_parse_json(raw: str) -> Dict[str, Any]:
    text = raw.strip()

    # Strip ```json fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

        if text.lower().startswith("json"):
            text = text[4:].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    return {
        "error": "Model did not return valid JSON",
        "raw": raw,
    }


@mcp.tool
def build_prompt_package(
    raw_chat: str,
    detail_level: str = "medium",
    max_examples: int = 3,
    tone: str = "neutral",
    target_use: str = "single_prompt",
    language: str = "en",
) -> Dict[str, Any]:
    """
    Main tool: given the full conversation and settings, call Gemini 2.0 Flash to:
      - Summarize the conversation
      - Extract structured context
      - Pick examples
      - Build a reusable final prompt

    Returns:
      {
        "summary": "...",
        "context": {...},
        "examples": [...],
        "final_prompt": "...",
        "usage_notes": "..."
      }
      or an error object.
    """

    if not raw_chat or not raw_chat.strip():
        return {"error": "raw_chat is empty"}

    detail_level = _sanitize_setting(detail_level, ["short", "medium", "long"], "medium")
    tone = _sanitize_setting(tone, ["neutral", "friendly", "formal"], "neutral")
    target_use = _sanitize_setting(target_use, ["system_prompt", "single_prompt"], "single_prompt")

    try:
        max_examples_int = int(max_examples)
    except Exception:
        max_examples_int = 3
    max_examples_int = max(0, min(max_examples_int, 10))

    user_content, _ = build_user_content(
        raw_chat=raw_chat,
        detail_level=detail_level,
        max_examples=max_examples_int,
        tone=tone,
        target_use=target_use,
        language=language,
    )

    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL_NAME,
            system_instruction=PACKAGER_SYSTEM_PROMPT,
        )

        response = model.generate_content(
            user_content,
            generation_config={"temperature": 0.2},
        )

        raw_output = (response.text or "").strip()
        if not raw_output:
            return {"error": "Gemini returned empty response"}

        data = _safe_parse_json(raw_output)
        return data

    except Exception as e:
        return {"error": f"Exception while calling Gemini: {str(e)}"}


if __name__ == "__main__":
    mcp.run()
