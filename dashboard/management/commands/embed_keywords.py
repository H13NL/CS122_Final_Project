from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from cs122_final_project import embeddings
from cs122_final_project.database import Database


class Command(BaseCommand):
    help = "Cache sentence embeddings for every stored sentiment keyword."

    def add_arguments(self, parser):
        parser.add_argument(
            "--video",
            help="Only embed keywords belonging to this video ID.",
        )
        parser.add_argument(
            "--model",
            help="Override the configured sentence-transformers model.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=embeddings.DEFAULT_BATCH_SIZE,
            help="Number of keywords encoded per batch.",
        )
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Delete cached vectors for the model before embedding.",
        )

    def handle(self, *args, **options):
        database_path = getattr(
            settings,
            "DATABASE_PATH",
            settings.BASE_DIR / "database.db",
        )
        model = options["model"] or embeddings.model_name()
        batch_size = max(options["batch_size"], 1)

        with Database(database_path) as db:
            if options["rebuild"]:
                db.clear_keyword_embeddings(model)

            keywords = db.distinct_keywords(options["video"])
            cached = db.get_keyword_embeddings(model, keywords)
            pending = [keyword for keyword in keywords if keyword not in cached]

            if not pending:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"All {len(keywords)} keywords already have "
                        f"embeddings for {model}"
                    )
                )
                return

            dim = embeddings.embedding_dim(model)
            embedded = 0

            for start in range(0, len(pending), batch_size):
                batch = pending[start:start + batch_size]
                vectors = embeddings.encode(
                    batch,
                    batch_size=batch_size,
                    name=model,
                )

                if vectors.shape != (len(batch), dim):
                    raise CommandError(
                        f"Model {model} returned shape {vectors.shape}, "
                        f"expected {(len(batch), dim)}"
                    )

                db.save_keyword_embeddings(
                    (
                        keyword,
                        model,
                        int(vector.size),
                        embeddings.to_blob(vector),
                        embeddings.vector_norm(vector),
                    )
                    for keyword, vector in zip(batch, vectors)
                )

                embedded += len(batch)
                self.stdout.write(
                    f"Embedded {embedded}/{len(pending)} pending keywords"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Cached {embedded} keyword embeddings with {model}"
            )
        )
