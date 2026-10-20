"""
comment dataclass
stores the attributes we keep for a single YouTube comment
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Comment:
    comment_id: str
    video_id: str
    text: str
    author: str
    like_count: int
    published_at: str

    @classmethod
    def from_api_item(cls, item: dict, video_id: str) -> "Comment":
        snippet = item.get("snippet", {})
        top = snippet.get("topLevelComment", {})
        top_snippet = top.get("snippet", {})
        return cls(
            comment_id=top.get("id", item.get("id", "")),
            video_id=video_id,
            text=top_snippet.get("textDisplay", ""),
            author=top_snippet.get("authorDisplayName", ""),
            like_count=int(top_snippet.get("likeCount", 0)),
            published_at=top_snippet.get("publishedAt", ""),
        )

    def printInfo(self) -> None:
        print(f"Comment by {self.author}: {self.text}.")
