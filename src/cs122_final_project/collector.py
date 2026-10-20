import os
import logging
from typing import List

from dotenv import load_dotenv
from googleapiclient.discovery import build

from .channel import Channel
from .comments import Comment
from .video import Video
from .database import Database

MAX_COMMENTS_PER_VIDEO = 100


def fetch_comments(video_id: str, youtube, max_comments: int = MAX_COMMENTS_PER_VIDEO) -> List[Comment]:
    comments = []
    nextPageToken = None
    try:
        while len(comments) < max_comments:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=min(100, max_comments - len(comments)),
                pageToken=nextPageToken,
                textFormat="plainText",
            )
            response = request.execute()
            for item in response.get("items", []):
                comments.append(Comment.from_api_item(item, video_id))
            nextPageToken = response.get("nextPageToken")
            if not nextPageToken:
                break
    except Exception as e:
        print(f"Error fetching comments for video {video_id}: {e}")
    return comments


def get_channel_by_id(channel_id: str, youtube) -> Channel | None:
    try:
        request = youtube.channels().list(
            part="snippet,contentDetails,statistics",
            id=channel_id,
        )
        response = request.execute()
        if response.get("items"):
            return Channel.from_api_item(response["items"][0])
        print(f"No channel found for channel ID: {channel_id}")
    except Exception as e:
        print(f"Error for channel {channel_id}: {e}")
    return None


def fetch_video(video_id: str, youtube) -> Video | None:
    try:
        request = youtube.videos().list(
            part="id,snippet,contentDetails,statistics,status",
            id=video_id,
        )
        response = request.execute()

        if response.get("items"):
            item = response["items"][0]
            statistics = item.get("statistics", {})

            video = Video(
                video_id=item["id"],
                channel_id=item["snippet"]["channelId"],
                title=item["snippet"]["title"],
                description=item["snippet"]["description"],
                publish_date=item["snippet"]["publishedAt"],
                views=int(statistics.get("viewCount", 0)),
                likes=int(statistics.get("likeCount", 0)),
                total_comments=int(statistics.get("commentCount", 0)),
                comments=fetch_comments(item["id"], youtube),
                duration=item["contentDetails"].get("duration", ""),
            )
            return video

        print(f"No video found for ID: {video_id}")
    except Exception as e:
        print(f"Error fetching data for video {video_id}: {e}")
    return None


def create_youtube_client(logger: logging.Logger):
    load_dotenv()
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise ValueError(
            "API_KEY not found in environment variables. Please check your .env file."
        )
    client = build("youtube", "v3", developerKey=api_key)
    logger.info("YouTube API client created successfully")
    return client


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("logs/collector.log"),
            logging.StreamHandler(),
        ],
    )
    logger = logging.getLogger(__name__)

    youtube = create_youtube_client(logger)

    video_id = input("Enter YouTube video ID: ").strip()

    video = fetch_video(video_id, youtube)
    if not video:
        logger.error("Failed to fetch video %s", video_id)
        return

    channel = get_channel_by_id(video.channel_id, youtube)

    with Database() as db:
        if channel:
            db.insert_channel(channel)
        db.insert_video(video)
        db.insert_many(comments=video.comments)

    logger.info(
        "Collected video %s (channel %s) with %d comments",
        video.video_id,
        video.channel_id,
        len(video.comments),
    )


if __name__ == "__main__":
    main()
