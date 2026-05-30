"""hindsight-sanitize — strip multimodal blobs from Hindsight retain content.

Image / audio user messages arrive as OpenAI-style content lists:

    [{"type":"text","text":"подпись"},
     {"type":"image_url","image_url":{"url":"data:image/png;base64,iVBOR..."}}]

Stringifying that verbatim pushes a multi-MB base64 blob into the bank
document — bloats Postgres, breaks embedding quality, recall returns junk
neighbours. This plugin wraps
``HindsightMemoryProvider._build_turn_messages`` so each non-text part is
replaced with a one-line placeholder (type + size hint) before retain
goes through.

All patching happens at ``register()`` time. No upstream files edited.
"""

from __future__ import annotations

import logging
from typing import Any, List

logger = logging.getLogger(__name__)


def _sanitize_for_retain(content: Any) -> str:
    """Squash multimodal content parts down to a retain-friendly string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out_parts: List[str] = []
        for part in content:
            if not isinstance(part, dict):
                out_parts.append(str(part))
                continue
            ptype = part.get("type", "")
            if ptype == "text":
                out_parts.append(str(part.get("text", "")))
            elif ptype == "image_url":
                url = part.get("image_url", {}).get("url", "") or ""
                if url.startswith("data:"):
                    mime = url.split(";", 1)[0].removeprefix("data:") or "image"
                    size_kb = max(1, len(url) // 1024)
                    out_parts.append(f"[image: {mime}, ~{size_kb}KB inline]")
                else:
                    out_parts.append(f"[image: {url[:120]}]")
            elif ptype in ("audio", "input_audio"):
                out_parts.append("[audio attachment]")
            else:
                out_parts.append(f"[{ptype or 'unknown'} part]")
        return "\n".join(p for p in out_parts if p)
    try:
        return str(content)
    except Exception:
        return ""


def register(ctx: Any) -> None:
    """Wrap HindsightMemoryProvider._build_turn_messages to sanitize content."""
    try:
        from plugins.memory.hindsight import HindsightMemoryProvider as HMP
    except Exception as exc:
        logger.error("hindsight-sanitize: cannot import HindsightMemoryProvider: %s", exc)
        return

    if getattr(HMP._build_turn_messages, "_sanitize_wrapped", False):
        logger.debug("hindsight-sanitize: already wrapped, skipping")
        return

    HMP._sanitize_for_retain = staticmethod(_sanitize_for_retain)

    _orig = HMP._build_turn_messages

    def _wrapped(self, user_content: Any, assistant_content: Any):
        user_text = _sanitize_for_retain(user_content)
        assistant_text = _sanitize_for_retain(assistant_content)
        return _orig(self, user_text, assistant_text)

    _wrapped._sanitize_wrapped = True  # type: ignore[attr-defined]
    HMP._build_turn_messages = _wrapped
    logger.info(
        "hindsight-sanitize: registered (HindsightMemoryProvider"
        "._build_turn_messages wrapped)"
    )
