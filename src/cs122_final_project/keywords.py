"""
collect multi-word key phrases using the RAKE (Rapid Automatic Keyword
Extraction) library

RAKE is run once, at collection time, over the text of a video's comments.
The resulting phrases are stored in the video_keywords table, separate from
the sentiment-family keywords produced by the analysis pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from rake_nltk import Rake

from .comments import Comment

logger = logging.getLogger(__name__)

DEFAULT_MAX_KEYWORDS = 25
MIN_PHRASE_WORDS = 1
MAX_PHRASE_WORDS = 4


@dataclass(frozen=True)
class Keyword:
    video_id: str
    phrase: str
    score: float
    rank: int


def extract_keywords(
    video_id: str,
    comments: Iterable[Comment],
    max_keywords: int = DEFAULT_MAX_KEYWORDS,
) -> list[Keyword]:
    """
    Extract ranked multi-word phrases from a video's comments.

    Returns an empty list when there is no usable comment text. Raises
    RuntimeError when the NLTK stopword corpus has not been downloaded.
    """
    sentences = [
        comment.text.strip()
        for comment in comments
        if comment.text and comment.text.strip()
    ]
    if not sentences:
        logger.warning(
            "No comment text for video %s; no keywords extracted", video_id
        )
        return []

    try:
        rake = Rake(
            min_length=MIN_PHRASE_WORDS,
            max_length=MAX_PHRASE_WORDS,
        )
    except LookupError as exc:
        raise RuntimeError(
            "NLTK stopwords are missing. Run: "
            "uv run python -m nltk.downloader stopwords"
        ) from exc

    # Passing each comment as its own sentence avoids NLTK's punkt sentence
    # tokenizer, which RAKE would otherwise require for a single text blob.
    rake.extract_keywords_from_sentences(sentences)

    seen: set[str] = set()
    keywords: list[Keyword] = []
    for score, phrase in rake.get_ranked_phrases_with_scores():
        if phrase in seen:
            continue
        seen.add(phrase)
        keywords.append(
            Keyword(
                video_id=video_id,
                phrase=phrase,
                score=float(score),
                rank=len(keywords) + 1,
            )
        )
        if len(keywords) == max_keywords:
            break

    return keywords
