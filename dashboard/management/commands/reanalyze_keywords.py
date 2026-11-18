from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from cs122_final_project.comments import Comment
from cs122_final_project.database import Database
from cs122_final_project.sentimentAnalysis import save_video_sentiment


class Command(BaseCommand):
    help = "Recompute significant sentiment keywords for stored videos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--video",
            help="Only reanalyze this video ID.",
        )

    def handle(self, *args, **options):
        database_path = getattr(
            settings,
            "DATABASE_PATH",
            settings.BASE_DIR / "database.db",
        )

        with Database(database_path) as db:
            videos = db.list_videos()

            if options["video"]:
                videos = [
                    video
                    for video in videos
                    if video["video_id"] == options["video"]
                ]

                if not videos:
                    raise CommandError(
                        f"Unknown video {options['video']!r}"
                    )

            if not videos:
                self.stdout.write("No videos have been collected yet.")
                return

            for video in videos:
                video_id = video["video_id"]
                rows = db.get_comments(
                    video_id=video_id,
                    limit=1_000_000,
                )
                comments = [
                    Comment(
                        comment_id=row["comment_id"],
                        video_id=row["video_id"],
                        text=row["text"],
                        author=row["author"],
                        like_count=row["like_count"],
                        published_at=row["published_at"],
                    )
                    for row in rows
                ]

                result = save_video_sentiment(db, video_id, comments)
                keywords = db.get_keywords(video_id)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"{video_id}: {len(comments)} comments, "
                        f"{len(keywords)} keywords, "
                        f"sentiment {result.sentiment} "
                        f"({result.score:.4f})"
                    )
                )
