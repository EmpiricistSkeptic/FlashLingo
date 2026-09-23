from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

LANGUAGE_CHOICES = [
    ("ru", "Russian"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
]

class LanguagePair(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="language_pairs")
    native_language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES)
    learning_language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "native_language", "learning_language"],
                name="unique_language_pair_per_user",
            ),
            models.CheckConstraint(
                condition=~models.Q(native_language=models.F("learning_language")),
                name="different_languages_in_pair",
            )
        ]


class Category(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="categories")
    language_pair = models.ForeignKey(LanguagePair, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "language_pair", "name"],
                name="unique_category_per_user"),
        ]

class Flashcard(models.Model):
    STATUS_CHOICES = (
        ("new", "New"),
        ("learning", "Learning"),
        ("learned", "Learned"),
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="flashcards",
    )

    categories = models.ManyToManyField(
        Category,
        related_name="flashcards",
        blank=True,
    )

    text = models.CharField(max_length=255)
    translations = models.JSONField(default=list)
    examples = models.JSONField(default=list)

    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default="new",
    )

    next_review = models.DateTimeField(null=True, blank=True)
    ease_factor = models.FloatField(default=2.5)
    interval = models.FloatField(default=0.0)  
    repetitions = models.PositiveIntegerField(default=0)
    learning_step = models.PositiveSmallIntegerField(default=0)
    review_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class UserProgress(models.Model):
    RESULT_CHOICES = [
        ("again", "Again"),
        ("hard", "Hard"),
        ("good", "Good"),
        ("easy", "Easy")
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="progress")
    flashcard = models.ForeignKey(Flashcard, on_delete=models.CASCADE, related_name="progress")
    result = models.CharField(max_length=10, choices=RESULT_CHOICES)
    interval_before = models.FloatField()
    ease_factor_before = models.FloatField()
    status_before = models.CharField(max_length=12)
    
    reviewed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.flashcard.text} - {self.result}"

class GameAttempt(models.Model):
    GAME_TYPE_CHOICES = (
        ("typing", "Typing"),
        ("sentence", "Sentence"),
        ("translation", "Translation"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="game_attempts",
    )

    flashcard = models.ForeignKey(
        Flashcard,
        on_delete=models.CASCADE,
        related_name="game_attempts",
    )

    game_type = models.CharField(
        max_length=12,
        choices=GAME_TYPE_CHOICES,
    )

    is_correct = models.BooleanField()

    user_answer = models.TextField(
        max_length=1000,
    )

    # Typing: None.
    # AI games: 0.0 - 1.0.
    score = models.FloatField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "user",
                    "flashcard",
                    "game_type",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.game_type} - "
            f"{self.flashcard.text} - "
            f"{self.is_correct}"
        )




