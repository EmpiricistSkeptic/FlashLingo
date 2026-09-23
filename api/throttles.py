from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from rest_framework.throttling import (
    ScopedRateThrottle,
)

class TranslationThrottle(UserRateThrottle):
    scope = "translation"

class AuthThrottle(AnonRateThrottle):
    scope = "auth"

class AIGameThrottle(
    ScopedRateThrottle
):
    scope = "ai_games"