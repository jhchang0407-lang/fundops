"""FundOps Chat: Strategy Chat + Archive Q&A behind one conversational surface.

`handle_message` is the single entry point (pinned in the API contract). Mode
classification decides whether a message changes strategy, explores tradeoffs,
reads status, or asks the archive; every exchange is retained as conversation
evidence.
"""

from backend.chat.service import handle_message

__all__ = ["handle_message"]
