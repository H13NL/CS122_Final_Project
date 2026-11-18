"""
Significant sentiment keyword extraction.

A keyword has to clear two gates before it is stored:

1. It must survive the stopword and function-word filter. This is what keeps
   words such as "and", "or", and "but" out of the keyword list.
2. It must carry sentiment, either from the bundled TextBlob lexicon or from
   its semantic distance to positive and negative anchor words.

Sentence embeddings are cached through the keyword_embeddings table. They
classify words the lexicon does not know, such as slang, and provide the
strength used to rank keywords.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, NamedTuple, Optional

import numpy as np

from . import embeddings
from .comments import Comment
from .database import Database

logger = logging.getLogger(__name__)

POSITIVE = "positive"
NEGATIVE = "negative"

TOKEN_PATTERN = re.compile(r"[a-z]+(?:'[a-z]+)?")

MIN_TOKEN_LENGTH = 3
SHORT_TOKENS = {"ok"}
MIN_LEXICON_POLARITY = 0.3
NEGATION_WINDOW = 3
MAX_EMBEDDING_CANDIDATES = 300
EMBEDDING_ONLY_MIN_COUNT = 2
EMBEDDING_ONLY_MIN_MARGIN = 0.25

NEGATORS = {
    "not",
    "no",
    "never",
    "none",
    "nobody",
    "nothing",
    "neither",
    "nor",
    "without",
    "hardly",
    "barely",
    "cannot",
    "can't",
    "don't",
    "doesn't",
    "didn't",
    "isn't",
    "aren't",
    "wasn't",
    "weren't",
    "won't",
    "wouldn't",
    "shouldn't",
    "couldn't",
    "haven't",
    "hasn't",
    "hadn't",
    "ain't",
}

FUNCTION_WORDS = {
    "able",
    "actually",
    "also",
    "anyway",
    "anyways",
    "basically",
    "even",
    "ever",
    "full",
    "gonna",
    "gotta",
    "however",
    "literally",
    "many",
    "maybe",
    "meanwhile",
    "much",
    "nevertheless",
    "okay",
    "perhaps",
    "quite",
    "rather",
    "really",
    "regardless",
    "simply",
    "somewhat",
    "sound",
    "still",
    "then",
    "therefore",
    "though",
    "thus",
    "too",
    "very",
    "whether",
    "whole",
    "yeah",
    "yep",
    "yet",
}

FALLBACK_STOPWORDS = set(
    """
    a about above after again against all am an and any are as at be because
    been before being below between both but by can could did do does doing
    down during each few for from further had has have having he her here hers
    herself him himself his how i if in into is it its itself me more most my
    myself no nor of off on once only or other our ours ourselves out over own
    same she should so some such than that the their theirs them themselves
    then there these they this those through to under until up was we were what
    when where which while who whom why will with would you your yours yourself
    yourselves
    """.split()
)

POSITIVE_ANCHORS = (
    "love",
    "enjoy",
    "amazing",
    "great",
    "best",
    "beautiful",
    "recommend",
    "favorite",
    "awesome",
    "brilliant",
)

NEGATIVE_ANCHORS = (
    "boring",
    "terrible",
    "worst",
    "hate",
    "disappointing",
    "annoying",
    "waste",
    "awful",
    "horrible",
    "stupid",
)

# Words the bundled TextBlob lexicon misses but that are common in comments.
EXTRA_LEXICON = {
    "like": 1.0,
    "liked": 1.0,
    "likes": 1.0,
    "liking": 1.0,
    "dislike": -1.0,
    "disliked": -1.0,
    "dislikes": -1.0,
    "thank": 0.6,
    "thanks": 0.6,
    "thanked": 0.6,
    "appreciate": 0.6,
    "appreciated": 0.6,
    "appreciates": 0.6,
    "anxious": -0.6,
    "relaxed": 0.6,
    "relaxing": 0.6,
    "goated": 1.0,
    "mid": -0.5,
    "meh": -0.5,
}

# "like" is only a sentiment word when it is not a comparison preposition.
LIKE_PREPOSITION_CUES = {
    "look",
    "looked",
    "looking",
    "looks",
    "sound",
    "sounded",
    "sounding",
    "sounds",
    "feel",
    "feels",
    "felt",
    "feeling",
    "seem",
    "seemed",
    "seeming",
    "seems",
    "something",
    "anything",
    "nothing",
    "everything",
    "just",
    "more",
    "most",
    "much",
    "really",
    "kind",
    "sort",
    "would",
    "i'd",
    "you'd",
    "they'd",
    "we'd",
}


class KeywordScore(NamedTuple):
    keyword: str
    family: str
    comment_count: int
    score: float


@dataclass
class _PolarityStats:
    """Per-keyword sentiment evidence across a video's comments."""

    positive_count: int = 0
    negative_count: int = 0
    positive_weight: float = 0.0
    negative_weight: float = 0.0
    intrinsic_sign: int = 1


def _sign(value: float) -> int:
    return 1 if value > 0 else -1


def _load_stopwords() -> set[str]:
    try:
        from nltk.corpus import stopwords

        words = set(stopwords.words("english"))
    except LookupError:
        logger.warning(
            "NLTK stopwords are missing; using the built-in fallback list"
        )
        words = set(FALLBACK_STOPWORDS)

    return words | FUNCTION_WORDS


STOPWORDS = _load_stopwords()


def _load_lexicon():
    try:
        from textblob.en import sentiment

        return sentiment
    except Exception:
        logger.warning(
            "TextBlob sentiment lexicon unavailable; "
            "keywords will rely on embeddings only",
            exc_info=True,
        )
        return {}


LEXICON = _load_lexicon()


def lexicon_polarity(token: str) -> Optional[float]:
    """Return the lexicon polarity for one token, or None if unknown."""
    if token in EXTRA_LEXICON:
        return EXTRA_LEXICON[token]

    try:
        entry = LEXICON.get(token)
    except Exception:
        return None

    if not entry:
        return None

    assessment = entry.get(None)

    if assessment is None:
        assessment = next(iter(entry.values()))

    return float(assessment[0])


def _negated(tokens: list[str], index: int) -> bool:
    start = max(0, index - NEGATION_WINDOW)
    return any(token in NEGATORS for token in tokens[start:index])


def _is_like_preposition(tokens: list[str], index: int) -> bool:
    if tokens[index] != "like" or index == 0:
        return False

    return tokens[index - 1] in LIKE_PREPOSITION_CUES


def _lexicon_analysis(
    comments: Iterable[Comment],
) -> tuple[dict[str, _PolarityStats], Counter]:
    """Collect per-keyword sentiment evidence and unknown candidates."""
    stats: dict[str, _PolarityStats] = defaultdict(_PolarityStats)
    unknown_counts: Counter = Counter()

    for comment in comments:
        tokens = TOKEN_PATTERN.findall((comment.text or "").lower())
        per_comment: dict[str, float] = defaultdict(float)
        intrinsic: dict[str, float] = {}
        unknown: set[str] = set()

        for index, token in enumerate(tokens):
            if len(token) < MIN_TOKEN_LENGTH and token not in SHORT_TOKENS:
                continue

            if token in STOPWORDS or _is_like_preposition(tokens, index):
                continue

            value = lexicon_polarity(token)

            if value is None:
                unknown.add(token)
                continue

            if abs(value) < MIN_LEXICON_POLARITY:
                continue

            intrinsic.setdefault(token, value)

            if _negated(tokens, index):
                value = -value

            per_comment[token] += value

        for token, value in per_comment.items():
            keyword_stats = stats[token]
            keyword_stats.intrinsic_sign = _sign(intrinsic[token])

            if value > 0:
                keyword_stats.positive_count += 1
                keyword_stats.positive_weight += value
            elif value < 0:
                keyword_stats.negative_count += 1
                keyword_stats.negative_weight += -value

        for token in unknown:
            unknown_counts[token] += 1

    return stats, unknown_counts


def _load_vectors(
    db: Database,
    keywords: list[str],
    model: str,
) -> dict[str, np.ndarray]:
    """Load cached vectors and encode anything missing."""
    stored = db.get_keyword_embeddings(model, keywords)
    missing = [keyword for keyword in keywords if keyword not in stored]

    if missing:
        try:
            encoded = embeddings.encode(missing, name=model)
        except Exception:
            logger.warning(
                "Could not encode keyword embeddings; "
                "falling back to lexicon keywords only",
                exc_info=True,
            )
            encoded = None

        if encoded is not None:
            db.save_keyword_embeddings(
                (
                    keyword,
                    model,
                    int(vector.size),
                    embeddings.to_blob(vector),
                    embeddings.vector_norm(vector),
                )
                for keyword, vector in zip(missing, encoded)
            )

            for keyword, vector in zip(missing, encoded):
                stored[keyword] = {
                    "dim": int(vector.size),
                    "vector": embeddings.to_blob(vector),
                    "norm": embeddings.vector_norm(vector),
                }

    return {
        keyword: embeddings.from_blob(data["vector"], data["dim"])
        for keyword, data in stored.items()
    }


_CENTROID_CACHE: dict[str, tuple[np.ndarray, np.ndarray]] = {}


def _centroids(model: str) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Return normalized positive and negative anchor centroids."""
    if model in _CENTROID_CACHE:
        return _CENTROID_CACHE[model]

    try:
        positive = embeddings.encode(POSITIVE_ANCHORS, name=model)
        negative = embeddings.encode(NEGATIVE_ANCHORS, name=model)
    except Exception:
        logger.warning(
            "Could not encode sentiment anchors; "
            "falling back to lexicon keywords only",
            exc_info=True,
        )
        return None

    positive_centroid = positive.mean(axis=0)
    negative_centroid = negative.mean(axis=0)

    positive_centroid /= np.linalg.norm(positive_centroid)
    negative_centroid /= np.linalg.norm(negative_centroid)

    _CENTROID_CACHE[model] = (positive_centroid, negative_centroid)
    return _CENTROID_CACHE[model]


def _embedding_only_keywords(
    db: Database,
    unknown_counts: Counter,
    model: str,
) -> list[KeywordScore]:
    """Classify unknown candidates by semantic distance to the anchors."""
    candidates = [
        keyword
        for keyword, count in unknown_counts.most_common(
            MAX_EMBEDDING_CANDIDATES
        )
        if count >= EMBEDDING_ONLY_MIN_COUNT
    ]

    if not candidates:
        return []

    centroids = _centroids(model)

    if centroids is None:
        return []

    vectors = _load_vectors(db, candidates, model)
    positive_centroid, negative_centroid = centroids

    rows = []

    for keyword in candidates:
        vector = vectors.get(keyword)

        if vector is None:
            continue

        positive_similarity = float(np.dot(vector, positive_centroid))
        negative_similarity = float(np.dot(vector, negative_centroid))
        margin = abs(positive_similarity - negative_similarity)

        if margin < EMBEDDING_ONLY_MIN_MARGIN:
            continue

        family = (
            POSITIVE
            if positive_similarity > negative_similarity
            else NEGATIVE
        )
        count = unknown_counts[keyword]

        rows.append(
            KeywordScore(
                keyword=keyword,
                family=family,
                comment_count=count,
                score=round(count * margin, 4),
            )
        )

    return rows


def keyword_counts(
    db: Database,
    comments: Iterable[Comment],
    model: Optional[str] = None,
) -> list[tuple[str, str, int, float]]:
    """
    Return (keyword, family, comment_count, score) rows for one video.

    Lexicon words use the majority sentiment of the comments they appear in,
    with their dictionary polarity breaking ties. Unknown words are admitted
    only when their embedding clearly sits closer to one sentiment anchor set.
    """
    model = model or embeddings.model_name()
    comments = list(comments)

    stats, unknown_counts = _lexicon_analysis(comments)

    rows: list[KeywordScore] = []

    for keyword, keyword_stats in stats.items():
        positive_count = keyword_stats.positive_count
        negative_count = keyword_stats.negative_count
        total_count = positive_count + negative_count

        if total_count == 0:
            continue

        if positive_count > negative_count:
            family = POSITIVE
            majority_count = positive_count
            strength = keyword_stats.positive_weight / positive_count
        elif negative_count > positive_count:
            family = NEGATIVE
            majority_count = negative_count
            strength = keyword_stats.negative_weight / negative_count
        else:
            family = (
                POSITIVE
                if keyword_stats.intrinsic_sign > 0
                else NEGATIVE
            )
            majority_count = positive_count
            strength = (
                keyword_stats.positive_weight
                + keyword_stats.negative_weight
            ) / total_count

        if strength < MIN_LEXICON_POLARITY:
            continue

        rows.append(
            KeywordScore(
                keyword=keyword,
                family=family,
                comment_count=total_count,
                score=round(majority_count * strength, 4),
            )
        )

    rows.extend(_embedding_only_keywords(db, unknown_counts, model))

    rows.sort(key=lambda row: (-row.score, -row.comment_count, row.keyword))

    return [
        (row.keyword, row.family, row.comment_count, row.score)
        for row in rows
    ]
