"""
channel dataclass
stores channel attributes and maps YouTube API payloads to typed objects
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Channel:
    channel_id: str
    title: str
    country: str
    uploads_playlist_id: str
    email: Optional[str] = None

    @classmethod
    def from_api_item(cls, item: dict) -> "Channel":
        snippet = item.get("snippet", {})
        return cls(
            channel_id=item["id"],
            title=snippet.get("title", ""),
            country=snippet.get("country", "N/A"),
            uploads_playlist_id=item["contentDetails"]["relatedPlaylists"]["uploads"],
        )

    def printInfo(self) -> None:
        print(f"Channel title: {self.title}, Channel ID: {self.channel_id}.")
