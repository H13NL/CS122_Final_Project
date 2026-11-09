import logging
import os
import re
from typing import List
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from googleapiclient.discovery import build

from .channel import Channel
from .comments import Comment
from .video import Video
from .database import Database
from .keywords import extract_keywords
from .sentimentAnalysis import save_video_sentiment

MAX_COMMENTS_PER_VIDEO = 100

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_PATH_PREFIXES = {"shorts", "embed", "live", "v"}


def extract_video_id(value: str) -> str:
    """
    Return the 11-character video ID from a YouTube URL or raw video ID.

    Raises ValueError when the value is not a supported YouTube URL or ID.
    """
    value = value.strip()

    if VIDEO_ID_PATTERN.fullmatch(value):
        return value

    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.netloc.split("@")[-1].split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]

    path = parsed.path.rstrip("/")
    candidate = ""

    if host == "youtu.be":
        candidate = path.lstrip("/").split("/")[0]
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        if path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        else:
            parts = [part for part in path.split("/") if part]
            if len(parts) >= 2 and parts[0] in YOUTUBE_PATH_PREFIXES:
                candidate = parts[1]
    else:
        raise ValueError(
            "That is not a YouTube link. Paste a youtube.com or youtu.be "
            "URL, or an 11-character video ID."
        )

    if VIDEO_ID_PATTERN.fullmatch(candidate):
        return candidate

    raise ValueError(
        "Could not find a valid 11-character video ID in that YouTube link."
    )


def prompt_for_video_id() -> str:
    """Prompt until the user supplies a valid YouTube URL or video ID."""
    while True:
        value = input("Enter YouTube video URL or ID: ").strip()
        if not value:
            print("Please enter a YouTube URL or an 11-character video ID.")
            continue

        try:
            return extract_video_id(value)
        except ValueError as exc:
            print(exc)


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

def collect_video(
    value: str,
    logger: logging.Logger | None = None,
) -> str:
    """
    Collect one YouTube video and save its data, comments,
    keywords, and sentiment analysis.

    Returns the collected video's ID.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    video_id = extract_video_id(value)
    youtube = create_youtube_client(logger)

    with Database() as db:
        if db.has_video(video_id):
            logger.info(
                "Video %s already collected; skipping",
                video_id,
            )
            return video_id

        video = fetch_video(video_id, youtube)

        if not video:
            raise ValueError(
                f"Failed to fetch video {video_id}"
            )

        channel = get_channel_by_id(
            video.channel_id,
            youtube,
        )

        keywords = extract_keywords(
            video.video_id,
            video.comments,
        )

        if channel:
            db.insert_channel(channel)

        db.insert_video(video)

        logger.info(
            "Comments attached to video object: %d",
            len(video.comments),
        )

        db.insert_many(
            comments=video.comments,
        )

        saved_comments = db.con.execute(
            """
            SELECT COUNT(*)
            FROM comments
            WHERE video_id = ?
            """,
            (video.video_id,),
        ).fetchone()[0]

        logger.info(
            "Comments saved to database for %s: %d",
            video.video_id,
            saved_comments,
        )

        db.insert_video_keywords(keywords)

        sentiment = save_video_sentiment(
            db,
            video.video_id,
            video.comments,
        )

    logger.info(
        "Collected video %s (channel %s) with %d comments "
        "and %d keywords; sentiment %s (%.4f)",
        video.video_id,
        video.channel_id,
        len(video.comments),
        len(keywords),
        sentiment.sentiment,
        sentiment.score,
    )

    return video.video_id

def main() -> None:
    os.makedirs("logs", exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("logs/collector.log"),
            logging.StreamHandler(),
        ],
    )

    logger = logging.getLogger(__name__)

    try:
        value = input(
            "Enter YouTube video URL or ID: "
        ).strip()

        if not value:
            print(
                "Please enter a YouTube URL or an 11-character video ID."
            )
            return

        collect_video(value, logger)

    except (EOFError, KeyboardInterrupt):
        print()
        logger.info("Collection cancelled")

    except ValueError as exc:
        logger.error("%s", exc)


if __name__ == "__main__":
    main()
