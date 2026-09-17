"""
Retrains Algorithm 2 (weak-topic classifier) and refreshes Algorithm 3
(KNN recommendations) against whatever real data has accumulated —
the production counterpart to the training steps inside
`demo_pipeline`, meant to be run periodically rather than as part of
seeding demo data.

Run manually:
    python manage.py retrain_models

Run periodically: see the `scheduler` service in podman-compose.yml,
which loops this command every RETRAIN_INTERVAL_SECONDS (default: once
a day). A real deployment could swap that loop for a proper cron job
or a Celery beat schedule instead — the command itself doesn't care
who calls it or how often.
"""
from django.core.management.base import BaseCommand

from academics.models import Topic
from ml_engine.models import StudentTopicFeature
from ml_engine.services import feature_engineering, knn_recommender, weak_topic_classifier


class Command(BaseCommand):
    help = "Retrain the weak-topic classifier and refresh KNN recommendations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--model-type", default="logistic", choices=["logistic", "naive_bayes"],
            help="Which classifier to train (default: logistic)",
        )
        parser.add_argument(
            "--label-noise", type=float, default=0.15,
            help="See weak_topic_classifier.train() docstring. Default 0.15.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Rebuilding student-topic features..."))
        n = feature_engineering.rebuild_all_features()
        self.stdout.write(f"  Rebuilt {n} feature rows across {Topic.objects.count()} topics")

        self.stdout.write(self.style.NOTICE("Training weak-topic classifier..."))
        try:
            report = weak_topic_classifier.train(
                model_type=options["model_type"], label_noise=options["label_noise"],
            )
        except ValueError as e:
            self.stdout.write(self.style.WARNING(f"  Skipped: {e}"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"  Trained on {report.n_samples} samples | accuracy={report.accuracy} "
            f"precision={report.precision} recall={report.recall} f1={report.f1}"
        ))
        self.stdout.write(f"  Model saved to {weak_topic_classifier.MODEL_PATH}")

        self.stdout.write(self.style.NOTICE("Refreshing KNN recommendations..."))
        recs_made = 0
        for f in StudentTopicFeature.objects.filter(is_weak=True).select_related("student", "topic"):
            if knn_recommender.recommend_for_student(f.student, f.topic, k=5):
                recs_made += 1
        self.stdout.write(f"  Generated/updated {recs_made} recommendations")

        self.stdout.write(self.style.SUCCESS("Retraining complete."))
