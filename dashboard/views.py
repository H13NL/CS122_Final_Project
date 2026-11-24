import logging
import re

from django.conf import settings
from django.shortcuts import redirect, render
from django.utils.html import escape
from django.utils.safestring import mark_safe

from cs122_final_project.database import SENTIMENT_LABELS, Database
from cs122_final_project.collector import (
    collect_video,
    extract_video_id,
)

logger = logging.getLogger(__name__)


# Create your views here.
DATABASE_PATH = settings.BASE_DIR / "database.db"

EXPLORER_PAGE_SIZES = (25, 50, 100)
EXPLORER_SENTIMENTS = SENTIMENT_LABELS + ("unscored",)
EXPLORER_SORT_OPTIONS = (
    ("published_at", "Newest first"),
    ("like_count", "Most liked"),
    ("sentiment_score", "Sentiment score"),
    ("author", "Author"),
)
EXPLORER_SORT_KEYS = {value for value, _ in EXPLORER_SORT_OPTIONS}
MAX_SEARCH_LENGTH = 200
MAX_KEYWORD_LENGTH = 64
MAX_HIGHLIGHT_TERMS = 10


def _int_param(value, default, minimum=None):
    """Parse an integer query parameter, falling back to a default."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default

    if minimum is not None and number < minimum:
        return default

    return number


def highlight(text: str, terms) -> str:
    """Escape comment text and wrap search terms in <mark> elements."""
    text = text or ""

    terms = [term for term in terms if term]
    if not terms:
        return str(escape(text))

    pattern = re.compile(
        "(" + "|".join(re.escape(term) for term in terms) + ")",
        re.IGNORECASE,
    )

    parts = pattern.split(text)

    return mark_safe(
        "".join(
            f"<mark>{escape(part)}</mark>" if index % 2 else str(escape(part))
            for index, part in enumerate(parts)
        )
    )

def home(request):
    return render(
        request,
        "dashboard/home.html",
    )


def fetch_video(request):
    if request.method != "POST":
        return redirect("home")

    value = request.POST.get("url", "").strip()

    if not value:
        return render(
            request,
            "dashboard/home.html",
            {
                "error": "Please enter a YouTube URL."
            },
        )

    try:
        video_id = extract_video_id(value)
        collect_video(video_id, logger)

    except ValueError as exc:
        return render(
            request,
            "dashboard/home.html",
            {
                "error": str(exc)
            },
        )

    return redirect("overview")


def overview(request, video_id=None):
    with Database(DATABASE_PATH) as db:
        if video_id:
            video = db.get_video(video_id)
            videos = [video] if video else []
        else:
            videos = db.list_videos()

    return render(
        request,
        "dashboard/overview.html",
        {"videos": videos},
    )


def analysis(request, video_id):
    with Database(DATABASE_PATH) as db:
        video = db.get_video(video_id)

        if video is None:
            return render(
                request,
                "dashboard/analysis.html",
                {
                    "error": "Video was not found."
                },
            )

        distribution = db.sentiment_distribution(video_id)
        keywords = db.get_keywords(
            video_id,
            limit=10,
        )

    return render(
        request,
        "dashboard/analysis.html",
        {
            "video": video,
            "distribution": distribution,
            "keywords": keywords,
        },
    )


def comparison(request):
    selected_video_ids = request.GET.getlist("videos")

    with Database(DATABASE_PATH) as db:
        videos = db.list_videos()
        comparison_results = db.compare_videos(
            selected_video_ids,
            top_n=5,
        )

    return render(
        request,
        "dashboard/comparison.html",
        {
            "videos": videos,
            "comparison_results": comparison_results,
            "selected_video_ids": selected_video_ids,
        },
    )


def explorer(request):
    """Browse and filter comments across every collected video."""
    video_id = request.GET.get("video", "").strip()
    search = request.GET.get("q", "").strip()[:MAX_SEARCH_LENGTH]
    sentiment = request.GET.get("sentiment", "").strip()
    keyword = request.GET.get("keyword", "").strip()[:MAX_KEYWORD_LENGTH]
    min_likes = _int_param(request.GET.get("min_likes"), None, minimum=0)

    sort = request.GET.get("sort", "published_at").strip()
    if sort not in EXPLORER_SORT_KEYS:
        sort = "published_at"

    descending = request.GET.get("direction", "desc") != "asc"

    page = _int_param(request.GET.get("page"), 1, minimum=1)

    page_size = _int_param(request.GET.get("page_size"), 25)
    if page_size not in EXPLORER_PAGE_SIZES:
        page_size = 25

    if sentiment not in EXPLORER_SENTIMENTS:
        sentiment = ""

    filters = {
        "video_id": video_id or None,
        "sentiment": sentiment or None,
        "search": search or None,
        "keyword": keyword or None,
        "min_likes": min_likes,
    }

    with Database(DATABASE_PATH) as db:
        videos = db.list_videos()

        if video_id and not any(
            video["video_id"] == video_id for video in videos
        ):
            return render(
                request,
                "dashboard/explorer.html",
                {
                    "videos": videos,
                    "error": "Video was not found.",
                },
            )

        total = db.count_comments(**filters)
        pages = max((total + page_size - 1) // page_size, 1)
        page = min(page, pages)

        rows = db.get_comments(
            **filters,
            order_by=sort,
            descending=descending,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        facets = db.sentiment_facets(**{
            key: value
            for key, value in filters.items()
            if key != "sentiment"
        })
        facets["all"] = sum(facets.values())
        keyword_rows = db.keyword_options(video_id or None)

    terms = search.split()
    if keyword:
        terms.append(keyword)
    terms = terms[:MAX_HIGHLIGHT_TERMS]
    for row in rows:
        row["highlighted_text"] = highlight(row.get("text"), terms)

    keyword_groups = [
        (
            family,
            [row for row in keyword_rows if row["family"] == family],
        )
        for family in ("positive", "negative")
    ]
    keyword_groups = [
        (family, group) for family, group in keyword_groups if group
    ]

    query = {
        "video": video_id,
        "q": search,
        "sentiment": sentiment,
        "keyword": keyword,
        "min_likes": "" if min_likes is None else min_likes,
        "sort": sort,
        "direction": "asc" if not descending else "desc",
        "page_size": page_size,
    }

    return render(
        request,
        "dashboard/explorer.html",
        {
            "videos": videos,
            "rows": rows,
            "total": total,
            "page": page,
            "pages": pages,
            "prev_page": page - 1 if page > 1 else None,
            "next_page": page + 1 if page < pages else None,
            "page_size": page_size,
            "page_sizes": EXPLORER_PAGE_SIZES,
            "facets": facets,
            "keyword_groups": keyword_groups,
            "sentiments": EXPLORER_SENTIMENTS,
            "sort_options": EXPLORER_SORT_OPTIONS,
            "query": query,
            "has_filters": any(
                (
                    video_id,
                    search,
                    sentiment,
                    keyword,
                    min_likes is not None,
                )
            ),
        },
    )
