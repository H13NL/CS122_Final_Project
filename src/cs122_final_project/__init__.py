"""cs122_final_project: YouTube comment sentiment collection and analysis."""

from .channel import Channel
from .comments import Comment
from .video import Video
from .database import Database


def main() -> None:
    from .collector import main as collector_main

    collector_main()


__all__ = ["Channel", "Comment", "Video", "Database", "main"]
