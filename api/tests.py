from django.test import TestCase

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import Flashcard
from .services import sr_config as cfg
from .services.spaced_repetition import review_flashcard

User = get_user_model()


def make_flashcard(user, **overrides):
    defaults = dict(text="hola", translations=["hello"], examples=[])
    defaults.update(overrides)
    return Flashcard.objects.create(user=user, **defaults)


class SpacedRepetitionServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ana", password="pw")

    def test_new_card_again_starts_short_learning_interval(self):
        card = make_flashcard(self.user)
        review_flashcard(card, "again")
        self.assertEqual(card.status, "learning")
        self.assertAlmostEqual(card.interval, cfg.AGAIN_INTERVAL_DAYS)
        self.assertEqual(card.repetitions, 0)
        self.assertEqual(card.review_count, 1)
        self.assertLess(card.ease_factor, 2.5)

    def test_new_card_good_is_longer_than_again(self):
        again_card = make_flashcard(self.user)
        review_flashcard(again_card, "again")

        good_card = make_flashcard(self.user)
        review_flashcard(good_card, "good")

        self.assertGreater(good_card.interval, again_card.interval)
        self.assertEqual(good_card.status, "learning")
        self.assertEqual(good_card.repetitions, 1)
        self.assertEqual(again_card.learning_step, 0)
        self.assertEqual(good_card.learning_step, 1)

    def test_new_card_hard_is_between_again_and_good(self):
        again_card = make_flashcard(self.user)
        hard_card = make_flashcard(self.user)
        good_card = make_flashcard(self.user)

        review_flashcard(again_card, "again")
        review_flashcard(hard_card, "hard")
        review_flashcard(good_card, "good")

        self.assertLess(again_card.interval, hard_card.interval)
        self.assertLess(hard_card.interval, good_card.interval)

    def test_new_card_easy_graduates_immediately(self):
        card = make_flashcard(self.user)
        review_flashcard(card, "easy")
        self.assertEqual(card.status, "learned")
        self.assertEqual(card.interval, cfg.EASY_GRADUATING_INTERVAL_DAYS)
        self.assertGreater(card.ease_factor, 2.5)

    def test_card_graduates_after_completing_learning_steps(self):
        card = make_flashcard(self.user)
        review_flashcard(card, "good")  # -> step 1 (1 hour)
        self.assertEqual(card.status, "learning")
        self.assertEqual(card.learning_step, 1)
        review_flashcard(card, "good")  # -> step 2 (1 day)
        self.assertEqual(card.status, "learning")
        self.assertEqual(card.learning_step, 2)
        review_flashcard(card, "good")  # -> graduates
        self.assertEqual(card.status, "learned")
        self.assertEqual(card.interval, cfg.GRADUATING_INTERVAL_DAYS)
        self.assertEqual(card.repetitions, 3)
        self.assertEqual(card.learning_step, 0)  # reset on graduation

    def test_hard_does_not_advance_learning_step(self):
        card = make_flashcard(self.user)
        review_flashcard(card, "good")  # learning_step -> 1 (did the 1hr step)
        review_flashcard(card, "hard")  # should re-show the same step, not advance
        self.assertEqual(card.status, "learning")
        self.assertEqual(card.learning_step, 1)
        # repetitions still increases even though it's a "hard" press
        self.assertEqual(card.repetitions, 2)
        # next Good should still land on the 2nd step (1 day), proving
        # Hard didn't silently skip it
        review_flashcard(card, "good")
        self.assertEqual(card.interval, cfg.LEARNING_STEPS_DAYS[1])
        self.assertEqual(card.learning_step, 2)

    def test_again_resets_progress_mid_learning(self):
        card = make_flashcard(self.user)
        review_flashcard(card, "good")
        review_flashcard(card, "again")
        self.assertEqual(card.repetitions, 0)
        self.assertEqual(card.learning_step, 0)
        self.assertAlmostEqual(card.interval, cfg.AGAIN_INTERVAL_DAYS)

    def test_mature_good_grows_interval_by_ease_factor(self):
        card = make_flashcard(
            self.user, status="learned", interval=10.0, ease_factor=2.5, repetitions=5
        )
        review_flashcard(card, "good")
        self.assertEqual(card.interval, 25.0)  # 10 * 2.5
        self.assertEqual(card.repetitions, 6)
        self.assertEqual(card.status, "learned")

    def test_mature_hard_grows_much_less_than_good(self):
        good_card = make_flashcard(
            self.user, status="learned", interval=10.0, ease_factor=2.5, repetitions=5
        )
        hard_card = make_flashcard(
            self.user, status="learned", interval=10.0, ease_factor=2.5, repetitions=5
        )
        review_flashcard(good_card, "good")
        review_flashcard(hard_card, "hard")
        self.assertLess(hard_card.interval, good_card.interval)
        self.assertGreater(hard_card.interval, 10.0)  # still grows, just less

    def test_mature_easy_grows_more_than_good(self):
        good_card = make_flashcard(
            self.user, status="learned", interval=10.0, ease_factor=2.5, repetitions=5
        )
        easy_card = make_flashcard(
            self.user, status="learned", interval=10.0, ease_factor=2.5, repetitions=5
        )
        review_flashcard(good_card, "good")
        review_flashcard(easy_card, "easy")
        self.assertGreater(easy_card.interval, good_card.interval)

    def test_mature_again_is_a_lapse_back_to_learning(self):
        card = make_flashcard(
            self.user, status="learned", interval=60.0, ease_factor=2.6, repetitions=10
        )
        review_flashcard(card, "again")
        self.assertEqual(card.status, "learning")
        self.assertAlmostEqual(card.interval, cfg.AGAIN_INTERVAL_DAYS)
        self.assertEqual(card.repetitions, 0)
        self.assertEqual(card.learning_step, 0)
        self.assertLess(card.ease_factor, 2.6)

    def test_ease_factor_never_drops_below_minimum(self):
        card = make_flashcard(self.user, status="learned", interval=5.0, ease_factor=1.35)
        review_flashcard(card, "again")
        review_flashcard(card, "again")
        self.assertGreaterEqual(card.ease_factor, cfg.MIN_EASE_FACTOR)

    def test_ease_factor_never_exceeds_maximum(self):
        card = make_flashcard(self.user, status="learned", interval=5.0, ease_factor=3.45)
        review_flashcard(card, "easy")
        review_flashcard(card, "easy")
        self.assertLessEqual(card.ease_factor, cfg.MAX_EASE_FACTOR)

    def test_interval_is_capped_at_maximum(self):
        card = make_flashcard(
            self.user, status="learned", interval=300.0, ease_factor=3.5, repetitions=20
        )
        review_flashcard(card, "easy")
        self.assertLessEqual(card.interval, cfg.MAX_INTERVAL_DAYS)

    def test_review_count_increments_for_every_result(self):
        card = make_flashcard(self.user)
        for result in ["again", "hard", "good", "easy"]:
            before = card.review_count
            review_flashcard(card, result)
            self.assertEqual(card.review_count, before + 1)

    def test_review_count_and_repetitions_diverge_on_again(self):
        card = make_flashcard(self.user)
        review_flashcard(card, "good")   # repetitions=1, review_count=1
        review_flashcard(card, "again")  # repetitions=0, review_count=2
        self.assertEqual(card.review_count, 2)
        self.assertEqual(card.repetitions, 0)

    def test_invalid_result_raises(self):
        card = make_flashcard(self.user)
        with self.assertRaises(ValueError):
            review_flashcard(card, "excellent")

    def test_next_review_is_timezone_aware(self):
        card = make_flashcard(self.user)
        review_flashcard(card, "good")
        self.assertIsNotNone(card.next_review)
        self.assertTrue(timezone.is_aware(card.next_review))


class FlashcardReviewApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ana", password="pw")
        self.other_user = User.objects.create_user(username="beto", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_review_requires_authentication(self):
        card = make_flashcard(self.user)
        anon_client = APIClient()
        response = anon_client.post(
            f"/api/flashcards/{card.id}/review/", {"result": "good"}, format="json"
        )
        # 401 vs 403 depends on which DRF authentication classes are
        # configured (e.g. token/JWT auth -> 401, session auth alone -> 403).
        # Either way, the request must be rejected.
        self.assertIn(
            response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_review_rejects_invalid_result(self):
        card = make_flashcard(self.user)
        response = self.client.post(
            f"/api/flashcards/{card.id}/review/", {"result": "meh"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_review_updates_and_returns_card_state(self):
        card = make_flashcard(self.user)
        response = self.client.post(
            f"/api/flashcards/{card.id}/review/", {"result": "good"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "learning")
        self.assertEqual(response.data["result"], "good")

        card.refresh_from_db()
        self.assertEqual(card.status, "learning")

    def test_review_cannot_touch_another_users_card(self):
        other_card = make_flashcard(self.other_user)
        response = self.client.post(
            f"/api/flashcards/{other_card.id}/review/", {"result": "good"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_due_endpoint_only_returns_own_due_and_new_cards(self):
        now = timezone.now()

        due_card = make_flashcard(
            self.user, status="learned", interval=5.0, next_review=now - timedelta(days=1)
        )
        future_card = make_flashcard(
            self.user, status="learned", interval=5.0, next_review=now + timedelta(days=5)
        )
        new_card = make_flashcard(self.user)  # status="new", next_review=None
        make_flashcard(self.other_user)  # belongs to someone else

        response = self.client.get("/api/flashcards/study/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        due_ids = {c["id"] for c in response.data["due"]}
        new_ids = {c["id"] for c in response.data["new"]}

        self.assertIn(due_card.id, due_ids)
        self.assertNotIn(future_card.id, due_ids)
        self.assertIn(new_card.id, new_ids)
