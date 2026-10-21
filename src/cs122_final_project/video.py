"""
video class object
store video attributes and class methods
"""

from dataclasses import dataclass, field
from typing import List

from .comments import Comment


@dataclass(frozen=True)
class Video:
    video_id: str
    channel_id: str
    title: str
    description: str
    publish_date: str
    views: int
    likes: int
    total_comments: int
    comments: List[Comment] = field(default_factory=list)
    duration: str = ""

    def printInfo(self) -> None:
        print(f"Video title: {self.title}, Video Description: {
              self.description}.")
