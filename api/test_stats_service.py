from datetime import timedelta, datetime
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch

from api.models import User, LanguagePair, Category, Flashcard, UserProgress
from api.services import stats_service

def create_progress(user, card, result, reviewed_at=None):
    """Вспомогательная функция для создания прогресса со всеми обязательными полями"""
    progress = UserProgress.objects.create(
        user=user, 
        flashcard=card, 
        result=result,
        ease_factor_before=2.5,
        interval_before=0.0,
        status_before="new"  # <--- Добавили это поле
    )
    if reviewed_at:
        progress.reviewed_at = reviewed_at
        progress.save(update_fields=['reviewed_at'])
    return progress

class TestStatsService(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="testuser")
        self.pair = LanguagePair.objects.create(user=self.user, native_language="en", learning_language="es")
        self.cat1 = Category.objects.create(user=self.user, name="Verbs", language_pair=self.pair)
        self.cat2 = Category.objects.create(user=self.user, name="Basics", language_pair=self.pair)
        
        self.card1 = Flashcard.objects.create(user=self.user, text="Hablar", status="new", ease_factor=2.5)
        self.card1.categories.add(self.cat1)
        
        self.card2 = Flashcard.objects.create(user=self.user, text="Gato", status="learned", ease_factor=2.5)
        self.card2.categories.add(self.cat2)

    def test_accuracy_and_total_zero_reviews(self):
        qs = UserProgress.objects.filter(user=self.user)
        accuracy, total = stats_service._accuracy_and_total(qs)
        self.assertEqual(total, 0)
        self.assertIsNone(accuracy)

    def test_accuracy_and_total_m2m_duplication_prevention(self):
        self.card1.categories.add(self.cat2)
        create_progress(self.user, self.card1, "good")
        
        qs = UserProgress.objects.filter(
            user=self.user, 
            flashcard__categories__language_pair=self.pair
        )
        accuracy, total = stats_service._accuracy_and_total(qs)
        
        self.assertEqual(total, 1)
        self.assertEqual(accuracy, 1.0)

    @patch('django.utils.timezone.now')
    def test_compute_streak(self, mock_now):
        # Замораживаем время через mock
        base_time = timezone.make_aware(datetime(2026, 8, 30, 12, 0, 0))
        mock_now.return_value = base_time

        # 1. Нет ревью
        streak = stats_service._compute_streak(self.user)
        self.assertEqual(streak, {"current": 0, "longest": 0})

        # 2. Ревью сегодня и 3 дня назад
        create_progress(self.user, self.card1, "good", reviewed_at=base_time)
        create_progress(self.user, self.card1, "good", reviewed_at=base_time - timedelta(days=3))
        
        streak = stats_service._compute_streak(self.user)
        self.assertEqual(streak["current"], 1)
        self.assertEqual(streak["longest"], 1)

        # 3. Ревью вчера -> current должен быть 2, grace period работает
        create_progress(self.user, self.card1, "good", reviewed_at=base_time - timedelta(days=1))
        streak = stats_service._compute_streak(self.user)
        self.assertEqual(streak["current"], 2)
        self.assertEqual(streak["longest"], 2)

    @patch('django.utils.timezone.now')
    def test_compute_streak_grace_period(self, mock_now):
        base_time = timezone.make_aware(datetime(2026, 8, 30, 12, 0, 0))
        mock_now.return_value = base_time

        create_progress(self.user, self.card1, "good", reviewed_at=base_time - timedelta(days=1))
        create_progress(self.user, self.card1, "good", reviewed_at=base_time - timedelta(days=2))
        
        streak = stats_service._compute_streak(self.user)
        self.assertEqual(streak["current"], 2)

    def test_get_difficult_cards(self):
        card_ignored = Flashcard.objects.create(user=self.user, text="New")

        # Карточка 1: 4 ревью, 3 again (again_rate = 0.75)
        for _ in range(3):
            create_progress(self.user, self.card1, "again")
        create_progress(self.user, self.card1, "good")

        # Карточка 2: 3 ревью, 1 again (again_rate = 0.33)
        create_progress(self.user, self.card2, "again")
        create_progress(self.user, self.card2, "good")
        create_progress(self.user, self.card2, "easy")

        # Карточка 3: 2 ревью, 2 again (игнорируем, т.к. ревью < 3)
        create_progress(self.user, card_ignored, "again")
        create_progress(self.user, card_ignored, "again")

        results = stats_service.get_difficult_cards(self.user, limit=5)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["flashcard_id"], self.card1.id)
        self.assertEqual(results[0]["again_rate"], 0.75)
        self.assertEqual(results[1]["flashcard_id"], self.card2.id)
        self.assertEqual(results[1]["again_rate"], round(1/3, 4))

    def test_get_accuracy_trend(self):
        today = timezone.now()
        yesterday = today - timedelta(days=1)
        
        # Сегодня: 1 good, 1 again (50%)
        create_progress(self.user, self.card1, "good", reviewed_at=today)
        create_progress(self.user, self.card1, "again", reviewed_at=today)
        
        # Вчера: 2 good (100%)
        create_progress(self.user, self.card1, "good", reviewed_at=yesterday)
        create_progress(self.user, self.card1, "easy", reviewed_at=yesterday)

        trend = stats_service.get_accuracy_trend(self.user, days=3)
        
        self.assertEqual(len(trend), 3)
        self.assertEqual(trend[0]["reviews"], 0)
        self.assertIsNone(trend[0]["accuracy"])
        self.assertEqual(trend[1]["reviews"], 2)
        self.assertEqual(trend[1]["accuracy"], 1.0)
        self.assertEqual(trend[2]["reviews"], 2)
        self.assertEqual(trend[2]["accuracy"], 0.5)