import logging
from django.shortcuts import render
from django.conf import settings
from django.shortcuts import redirect, render
from django.conf import settings
from django.shortcuts import redirect, render
from cs122_final_project.comments import Comment
from cs122_final_project.database import Database
from cs122_final_project.sentimentAnalysis import save_video_sentiment
from cs122_final_project.collector import collect_video
from cs122_final_project.collector import (
    collect_video,
    extract_video_id,
)

logger = logging.getLogger(__name__)


# Create your views here.
DATABASE_PATH = settings.BASE_DIR / "database.db"

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

