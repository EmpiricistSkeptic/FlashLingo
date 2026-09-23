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
                        max_length=12,
                        choices=[
                            ("typing", "Typing"),
                            ("sentence", "Sentence"),
                            ("translation", "Translation"),
                        ],
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
                        null=True,
                        blank=True,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
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
                (
                    "flashcard",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="game_attempts",
                        to="api.flashcard",
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
                        name="gameattempt_user_flashcard_type_idx",
                    ),
                ],
            },
        ),
    ]