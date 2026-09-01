from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterAPIView,
    LoginAPIView,
    LogoutAPIView,
    CategoryViewSet,
    TranslationPreviewAPIView,
    FlashcardViewSet,
    LanguagePairViewSet
)
from .stats_views import(
    AccuracyTrendView,
    ProgressViewSet,
    StatsOverviewView,
    LanguageStatsView,
    CategoryStatsView,
    DifficultCardsView,
)

router = DefaultRouter()
router.register(r"language-pairs", LanguagePairViewSet, basename="language-pair")
router.register(r"category", CategoryViewSet, basename="category")
router.register(r"flashcards", FlashcardViewSet, basename="flashcard")
router.register(r"progress", ProgressViewSet, basename="progress")



urlpatterns = [
    path("", include(router.urls)),
    path("register/", RegisterAPIView.as_view(), name="register"),
    path("login/", LoginAPIView.as_view(), name="login"),
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("translation/preview/", TranslationPreviewAPIView.as_view(), name="translation-preview"),
    path("stats/trend/", AccuracyTrendView.as_view(), name="stats-trend"),
    path("stats/overview/", StatsOverviewView.as_view(), name="stats-overview"),
    path("stats/languages/", LanguageStatsView.as_view(), name="stats-languages"),
    path("stats/categories/", CategoryStatsView.as_view(), name="stats-categories"),
    path("stats/difficult-cards/", DifficultCardsView.as_view(), name="stats-difficult-cards"),
    
]