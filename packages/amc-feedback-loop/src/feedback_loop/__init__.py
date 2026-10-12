"""
Human Feedback Loop module — public API surface.

The host application only needs to import from this module:

    from feedback_loop import start_feedback_loop, FeedbackLoopConfig
    from feedback_loop.adapters import AbstractDatabaseAdapter, AbstractEvidenceAdapter
"""

from feedback_loop.api import start_feedback_loop
from feedback_loop.config import FeedbackLoopConfig

__all__ = [
    "start_feedback_loop",
    "FeedbackLoopConfig",
]
