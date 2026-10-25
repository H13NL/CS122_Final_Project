"""
SQLite persistence layer.

The Database class owns the connection, creates the schema, and exposes
insert helpers that accept the dataclasses defined alongside it. Keeping the
connection behind a class makes the collector testable (pass an in-memory path)
and keeps SQL out of the collection logic.
"""

from datetime import datetime, timezone
import sqlite3
from contextlib import closing
from typing import Iterable, Optional

from .channel import Channel
from .comments import Comment
from .video import Video

SENTIMENT_LABELS = ("positive", "negative", "neutral")

KEYWORD_FAMILIES = ("positive", "negative", "neutral")

COMMENT_SORT_COLUMNS = {
    "published_at",
    "like_count",
    "sentiment_score",
    "author",
}

SUMMARY_KEYS = (
    "comments_analyzed",
    "avg_sentiment",
    "positive_ratio",
    "negative_ratio",
    "sentiment_bin",
)

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
        fetched_at TEXT NOT NULL,
        sentiment_score REAL,
        sentiment_bin TEXT,
        comments_analyzed INTEGER,
        avg_sentiment REAL,
        positive_ratio REAL,
        negative_ratio REAL,
        PRIMARY KEY (video_id),
        FOREIGN KEY (channel_id)
            REFERENCES channels (channel_id)
    )""",
    """CREATE TABLE IF NOT EXISTS comments (
        comment_id TEXT NOT NULL,
        video_id TEXT NOT NULL,
        text TEXT,
        author TEXT,
        like_count INTEGER,
        published_at TEXT,
        sentiment_score REAL,
        sentiment_label TEXT,
        PRIMARY KEY (comment_id),
        FOREIGN KEY (video_id)
            REFERENCES videos (video_id)
    )""",
        """CREATE TABLE IF NOT EXISTS keywords (
        video_id TEXT NOT NULL,
        keyword TEXT NOT NULL,
        family TEXT NOT NULL,
        comment_count INTEGER NOT NULL,
        PRIMARY KEY (video_id, keyword),
        FOREIGN KEY (video_id)
            REFERENCES videos (video_id)
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
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.c.execute(
            """INSERT OR REPLACE INTO videos
            (video_id, channel_id, title, description, published_at,
                view_count, like_count, comment_count, duration, fetched_at,
                sentiment_score, sentiment_bin)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                fetched_at,
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

    def save_analysis(
        self,
        video_id: str,
        comment_scores: Iterable[tuple],
        keywords: Iterable[tuple],
        summary: dict,
    ) -> None:
        """
        Save sentiment-analysis results for one video.

        comment_scores:
            Tuples containing:
            (comment_id, sentiment_score, sentiment_label)

        keywords:
            Tuples containing:
            (keyword, family, comment_count)

        summary:
            Dictionary containing the keys in SUMMARY_KEYS.
        """

        values = [summary[key] for key in SUMMARY_KEYS]

        cursor = self.con.execute(
            """
            UPDATE videos
            SET
                comments_analyzed = ?,
                avg_sentiment = ?,
                positive_ratio = ?,
                negative_ratio = ?,
                sentiment_bin = ?
            WHERE video_id = ?
            """,
            (*values, video_id),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"Cannot save analysis: unknown video {video_id!r}"
            )

        self.con.executemany(
            """
            UPDATE comments
            SET
                sentiment_score = ?,
                sentiment_label = ?
            WHERE comment_id = ?
              AND video_id = ?
            """,
            [
                (score, label, comment_id, video_id)
                for comment_id, score, label in comment_scores
            ],
        )

        self.con.execute(
            "DELETE FROM keywords WHERE video_id = ?",
            (video_id,),
        )

        self.con.executemany(
            """
            INSERT INTO keywords
                (video_id, keyword, family, comment_count)
            VALUES (?, ?, ?, ?)
            """,
            [
                (video_id, keyword, family, count)
                for keyword, family, count in keywords
            ],
        )

        self.con.commit()

    def _query(
        self,
        sql: str,
        params: tuple = (),
    ) -> list:
        """Execute a query and return rows as dictionaries."""
        rows = self.con.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def has_video(self, video_id: str) -> bool:
        """Return True if the video exists."""
        row = self.con.execute(
            """
            SELECT 1
            FROM videos
            WHERE video_id = ?
            """,
            (video_id,),
        ).fetchone()

        return row is not None

    def get_video(self, video_id: str) -> Optional[dict]:
        """Return one video with its channel information."""
        rows = self._query(
            """
            SELECT
                v.*,
                c.title AS channel_title,
                c.country AS channel_country
            FROM videos v
            LEFT JOIN channels c
                ON c.channel_id = v.channel_id
            WHERE v.video_id = ?
            """,
            (video_id,),
        )

        return rows[0] if rows else None

    def list_videos(self) -> list:
        """Return all stored videos."""
        return self._query(
            """
            SELECT
                v.*,
                c.title AS channel_title,
                c.country AS channel_country
            FROM videos v
            LEFT JOIN channels c
                ON c.channel_id = v.channel_id
            ORDER BY v.fetched_at DESC, v.video_id
            """
        )

    @staticmethod
    def _comment_filter(
        video_id: str,
        sentiment: Optional[str],
        search: Optional[str],
    ):
        """Build the WHERE clause for comment queries."""
        where = ["video_id = ?"]
        params = [video_id]

        if sentiment is not None:
            if sentiment not in SENTIMENT_LABELS:
                raise ValueError(
                    f"sentiment must be one of {SENTIMENT_LABELS}"
                )

            where.append("sentiment_label = ?")
            params.append(sentiment)

        if search:
            escaped = (
                search
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )

            where.append("text LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped}%")

        return " AND ".join(where), params

    def get_comments(
        self,
        video_id: str,
        sentiment: Optional[str] = None,
        search: Optional[str] = None,
        order_by: str = "published_at",
        descending: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list:
        """Return a page of comments for the Comment Explorer."""
        if order_by not in COMMENT_SORT_COLUMNS:
            raise ValueError(
                f"order_by must be one of {COMMENT_SORT_COLUMNS}"
            )

        where, params = self._comment_filter(
            video_id,
            sentiment,
            search,
        )

        direction = "DESC" if descending else "ASC"

        return self._query(
            f"""
            SELECT *
            FROM comments
            WHERE {where}
            ORDER BY {order_by} {direction}, comment_id
            LIMIT ?
            OFFSET ?
            """,
            (*params, limit, offset),
        )

    def count_comments(
        self,
        video_id: str,
        sentiment: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        """Return the number of comments matching the filters."""
        where, params = self._comment_filter(
            video_id,
            sentiment,
            search,
        )

        row = self.con.execute(
            f"""
            SELECT COUNT(*)
            FROM comments
            WHERE {where}
            """,
            params,
        ).fetchone()

        return row[0]

    def get_keywords(
        self,
        video_id: str,
        family: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list:
        """Return keyword counts for a video."""
        sql = """
            SELECT keyword, family, comment_count
            FROM keywords
            WHERE video_id = ?
        """

        params = [video_id]

        if family is not None:
            if family not in KEYWORD_FAMILIES:
                raise ValueError(
                    f"family must be one of {KEYWORD_FAMILIES}"
                )

            sql += " AND family = ?"
            params.append(family)

        sql += """
            ORDER BY comment_count DESC, keyword ASC
        """

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        return self._query(sql, tuple(params))

    def sentiment_distribution(self, video_id: str) -> dict:
        """Return comment counts grouped by sentiment."""
        result = {
            "positive": 0,
            "negative": 0,
            "neutral": 0,
            "unscored": 0,
        }

        rows = self.con.execute(
            """
            SELECT sentiment_label, COUNT(*) AS count
            FROM comments
            WHERE video_id = ?
            GROUP BY sentiment_label
            """,
            (video_id,),
        )

        for row in rows:
            label = row["sentiment_label"]

            if label in result:
                result[label] += row["count"]
            else:
                result["unscored"] += row["count"]

        return result

    def comments_per_month(self, video_id: str) -> list:
        """Return the number of comments per month."""
        return self._query(
            """
            SELECT
                substr(published_at, 1, 7) AS month,
                COUNT(*) AS comment_count
            FROM comments
            WHERE video_id = ?
              AND published_at IS NOT NULL
              AND published_at != ''
            GROUP BY month
            ORDER BY month
            """,
            (video_id,),
        )

    def compare_videos(
        self,
        video_ids: Iterable[str],
        top_n: int = 5,
    ) -> list:
        """Return comparison information for multiple videos."""
        results = []

        for video_id in video_ids:
            video = self.get_video(video_id)

            if video is not None:
                video["top_keywords"] = self.get_keywords(
                    video_id,
                    limit=top_n,
                )

                results.append(video)

        return results