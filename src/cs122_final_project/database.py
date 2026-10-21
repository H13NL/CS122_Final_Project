"""
SQLite persistence layer.

The Database class owns the connection, creates the schema, and exposes
insert helpers that accept the dataclasses defined alongside it. Keeping the
connection behind a class makes the collector testable (pass an in-memory path)
and keeps SQL out of the collection logic.
"""

import sqlite3
from contextlib import closing

from .channel import Channel
from .comments import Comment
from .video import Video

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS channels (
        channel_id TEXT NOT NULL,
        title TEXT,
        country TEXT,
        email TEXT,
        PRIMARY KEY (channel_id)
    )""",
    """CREATE TABLE IF NOT EXISTS videos (
        video_id TEXT NOT NULL,
        channel_id TEXT NOT NULL,
        title TEXT,
        description TEXT,
        published_at TEXT,
        view_count INTEGER,
        like_count INTEGER,
        comment_count INTEGER,
        duration TEXT,
        sentiment_score REAL,
        sentiment_bin TEXT,
        PRIMARY KEY (video_id),
        FOREIGN KEY (channel_id) REFERENCES channels (channel_id)
    )""",
    """CREATE TABLE IF NOT EXISTS comments (
        comment_id TEXT NOT NULL,
        video_id TEXT NOT NULL,
        text TEXT,
        author TEXT,
        like_count INTEGER,
        published_at TEXT,
        PRIMARY KEY (comment_id),
        FOREIGN KEY (video_id) REFERENCES videos (video_id)
    )""",
)


class Database:
    def __init__(self, path: str = "database.db") -> None:
        self.path = path
        self.con = sqlite3.connect(self.path)
        self.con.execute("PRAGMA foreign_keys = 1")
        self.c = self.con.cursor()

    def initialize(self) -> None:
        for statement in SCHEMA:
            self.c.execute(statement)
        self.con.commit()

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> "Database":
        self.initialize()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.con.commit()
        self.close()

    def insert_channel(self, channel: Channel) -> None:
        self.c.execute(
            """INSERT OR REPLACE INTO channels
               (channel_id, title, country, email)
               VALUES (?, ?, ?, ?)""",
            (channel.channel_id, channel.title, channel.country, channel.email),
        )
        self.con.commit()

    def insert_video(self, video: Video) -> None:
        self.c.execute(
            """INSERT OR REPLACE INTO videos
               (video_id, channel_id, title, description, published_at,
                view_count, like_count, comment_count, duration,
                sentiment_score, sentiment_bin)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                video.video_id,
                video.channel_id,
                video.title,
                video.description,
                video.publish_date,
                video.views,
                video.likes,
                video.total_comments,
                video.duration,
                None,
                None,
            ),
        )
        self.con.commit()

    def insert_comment(self, comment: Comment) -> None:
        self.c.execute(
            """INSERT OR REPLACE INTO comments
               (comment_id, video_id, text, author, like_count, published_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                comment.comment_id,
                comment.video_id,
                comment.text,
                comment.author,
                comment.like_count,
                comment.published_at,
            ),
        )
        self.con.commit()

    def insert_many(self, channels=(), videos=(), comments=()) -> None:
        for channel in channels:
            self.insert_channel(channel)
        for video in videos:
            self.insert_video(video)
        for comment in comments:
            self.insert_comment(comment)
        self.con.commit()
