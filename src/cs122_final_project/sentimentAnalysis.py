"""
Keyword sentiment analysis.

TextBlob scores each comment's polarity. The prepopulated sentiment keyword
families are matched against the same comments to produce keyword counts.

This module runs once during initial collection, after RAKE keyword
extraction, and stores its results through Database.save_analysis().
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, NamedTuple, Sequence

from textblob import TextBlob

from .comments import Comment
from .database import KEYWORD_FAMILIES, SENTIMENT_LABELS, Database

logger = logging.getLogger(__name__)

POSITIVE_LABEL, NEGATIVE_LABEL, NEUTRAL_LABEL = SENTIMENT_LABELS

POSITIVE_THRESHOLD = 0.1
NEGATIVE_THRESHOLD = -0.1

POSITIVE_KEYWORDS = (
    "good",
    "love",
    "great",
    "best",
    "excellent",
    "amazing",
    "fantastic",
    "awesome",
    "positive",
    "happy",
    "enjoy",
    "like",
    "super",
    "wonderful",
    "beautiful",
    "perfect",
    "brilliant",
    "delightful",
    "cool",
    "nice",
)

NEGATIVE_KEYWORDS = (
    "bad",
    "hate",
    "terrible",
    "worst",
    "poor",
    "dislike",
    "awful",
    "negative",
    "frustrating",
    "annoying",
    "disappointing",
    "horrible",
    "trash",
    "sucks",
    "fail",
    "stupid",
    "ridiculous",
    "pathetic",
)

NEUTRAL_KEYWORDS = (
    "maybe",
    "perhaps",
    "also",
    "and",
    "but",
    "or",
    "so",
    "then",
    "just",
    "yet",
    "however",
    "indeed",
    "whether",
    "meanwhile",
    "regardless",
    "either",
    "neither",
    "somewhat",
    "a bit",
)

KEYWORDS_BY_FAMILY: dict[str, tuple[str, ...]] = {
    POSITIVE_LABEL: POSITIVE_KEYWORDS,
    NEGATIVE_LABEL: NEGATIVE_KEYWORDS,
    NEUTRAL_LABEL: NEUTRAL_KEYWORDS,
}

if set(KEYWORDS_BY_FAMILY) != set(KEYWORD_FAMILIES):
    raise ValueError(
        "KEYWORDS_BY_FAMILY must define exactly the families listed in "
        f"KEYWORD_FAMILIES: {KEYWORD_FAMILIES}"
    )


class VideoSentiment(NamedTuple):
    """A video-level sentiment label and mean comment polarity."""

    sentiment: str
    score: float


def _compile_keyword(keyword: str) -> re.Pattern[str]:
    """Build a word-boundary pattern for one keyword or phrase."""
    words = [re.escape(word) for word in keyword.split()]
    return re.compile(r"\b" + r"\s+".join(words) + r"\b", re.IGNORECASE)


_KEYWORD_PATTERNS: dict[str, re.Pattern[str]] = {
    keyword: _compile_keyword(keyword)
    for keywords in KEYWORDS_BY_FAMILY.values()
    for keyword in keywords
}


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


def keyword_counts(comments: Iterable[Comment]) -> list[tuple[str, str, int]]:
    """Count comments containing each prepopulated sentiment keyword."""
    comments = list(comments)
    counts = {keyword: 0 for keyword in _KEYWORD_PATTERNS}

    for comment in comments:
        text = comment.text or ""
        for keyword, pattern in _KEYWORD_PATTERNS.items():
            if pattern.search(text):
                counts[keyword] += 1

    rows = [
        (keyword, family, counts[keyword])
        for family in KEYWORD_FAMILIES
        for keyword in KEYWORDS_BY_FAMILY[family]
    ]
    rows.sort(
        key=lambda row: (
            KEYWORD_FAMILIES.index(row[1]),
            -row[2],
            row[0],
        )
    )
    return rows


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

    db.save_analysis(
        video_id,
        scored,
        keyword_counts(comments),
        summary,
    )

    logger.info(
        "Saved sentiment for video %s: %s (%.4f)",
        video_id,
        result.sentiment,
        result.score,
    )
    return result
