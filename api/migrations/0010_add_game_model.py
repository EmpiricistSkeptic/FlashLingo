from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0009_delete_userprofile"),
    ]

    operations = [
        migrations.CreateModel(
            name="GameAttempt",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "game_type",
                    models.CharField(
                        choices=[
                            ("typing", "Typing"),
                            ("sentence", "Sentence"),
                            ("translation", "Translation"),
                        ],
                        max_length=12,
                    ),
                ),
                (
                    "is_correct",
                    models.BooleanField(),
                ),
                (
                    "user_answer",
                    models.TextField(
                        max_length=1000,
                    ),
                ),
                (
                    "score",
                    models.FloatField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    "flashcard",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="game_attempts",
                        to="api.flashcard",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="game_attempts",
                        to="api.user",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=[
                            "user",
                            "flashcard",
                            "game_type",
                        ],
                    ),
                ],
            },
        ),
    ]