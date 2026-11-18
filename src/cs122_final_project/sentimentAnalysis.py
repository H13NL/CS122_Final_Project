"""
Keyword sentiment analysis.

TextBlob scores each comment's polarity. Significant sentiment keywords are
produced by keyword_significance, which combines the TextBlob lexicon with
sentence embeddings for words the lexicon does not know.

This module runs once during initial collection, after RAKE keyword
extraction, and stores its results through Database.save_analysis().
"""

from __future__ import annotations

import logging
from typing import Iterable, NamedTuple, Sequence

from textblob import TextBlob

from .comments import Comment
from .database import SENTIMENT_LABELS, Database
from .keyword_significance import keyword_counts

logger = logging.getLogger(__name__)

POSITIVE_LABEL, NEGATIVE_LABEL, NEUTRAL_LABEL = SENTIMENT_LABELS

POSITIVE_THRESHOLD = 0.1
NEGATIVE_THRESHOLD = -0.1


class VideoSentiment(NamedTuple):
    """A video-level sentiment label and mean comment polarity."""

    sentiment: str
    score: float


def _sentiment_label(polarity: float) -> str:
    if polarity > POSITIVE_THRESHOLD:
        return POSITIVE_LABEL
    if polarity < NEGATIVE_THRESHOLD:
        return NEGATIVE_LABEL
    return NEUTRAL_LABEL


def score_comment(text: str) -> tuple[float, str]:
    """Return the TextBlob polarity and sentiment label for one comment."""
    text = (text or "").strip()
    if not text:
        return 0.0, NEUTRAL_LABEL

    try:
        polarity = float(TextBlob(text).sentiment.polarity)
    except Exception:
        logger.warning(
            "TextBlob failed to score a comment; using neutral",
            exc_info=True,
        )
        return 0.0, NEUTRAL_LABEL

    polarity = round(polarity, 4)
    return polarity, _sentiment_label(polarity)


def _score_comments(
    comments: Iterable[Comment],
) -> list[tuple[str, float, str]]:
    return [
        (comment.comment_id, *score_comment(comment.text))
        for comment in comments
    ]


def _aggregate(scored: Sequence[tuple[str, float, str]]) -> VideoSentiment:
    if not scored:
        return VideoSentiment(NEUTRAL_LABEL, 0.0)

    score = round(sum(item[1] for item in scored) / len(scored), 4)
    return VideoSentiment(_sentiment_label(score), score)


def analyze_video_sentiment(comments: Iterable[Comment]) -> VideoSentiment:
    """Return the aggregate sentiment label and score for a video."""
    return _aggregate(_score_comments(comments))


def save_video_sentiment(
    db: Database,
    video_id: str,
    comments: Iterable[Comment],
) -> VideoSentiment:
    """
    Analyze one video and persist the results.

    Returns the video-level sentiment label and mean comment polarity.
    """
    comments = list(comments)
    scored = _score_comments(comments)
    result = _aggregate(scored)
    total = len(scored)

    positive = sum(1 for _, _, label in scored if label == POSITIVE_LABEL)
    negative = sum(1 for _, _, label in scored if label == NEGATIVE_LABEL)

    summary = {
        "comments_analyzed": total,
        "avg_sentiment": result.score,
        "positive_ratio": round(positive / total, 4) if total else 0.0,
        "negative_ratio": round(negative / total, 4) if total else 0.0,
        "sentiment_bin": result.sentiment,
    }

    keywords = keyword_counts(db, comments)

    db.save_analysis(
        video_id,
        scored,
        keywords,
        summary,
    )

    logger.info(
        "Saved sentiment for video %s: %s (%.4f) with %d keywords",
        video_id,
        result.sentiment,
        result.score,
        len(keywords),
    )
    return result
