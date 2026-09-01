from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.db import transaction


from .models import (
    Category,
    Flashcard,
    UserProgress,
    LanguagePair
)

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]

class LanguagePairSerializer(serializers.ModelSerializer):
    class Meta:
        model = LanguagePair
        fields = ["id", "native_language", "learning_language", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

class CategorySerializer(serializers.ModelSerializer):
    card_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "language_pair", "card_count", "created_at", "updated_at"]
        read_only_fields = ["id", "card_count", "created_at", "updated_at"]

    def validate_language_pair(self, value):
        request = self.context["request"]
        if value.user_id != request.user.id:
            raise serializers.ValidationError(
                "Language pair does not belong to the current user."
            )
        return value

class FlashcardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flashcard
        fields = [
            "id",
            "categories",
            "text",
            "translations",
            "examples",
            "status",
            "next_review",
            "review_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "categories", "status", "next_review", "review_count", "created_at", "updated_at"]

class UserProgressSerializer(serializers.ModelSerializer):
    flashcard_text = serializers.CharField(source="flashcard.text", read_only=True)
    class Meta:
        model = UserProgress
        fields = [
            "id",
            "flashcard",
            "flashcard_text",
            "result",
            "interval_before",
            "ease_factor_before",
            "status_before",
            "reviewed_at",
        ]
        read_only_fields = fields

class RegisterSerializer(serializers.ModelSerializer):
    username = serializers.CharField(max_length=100)
    password = serializers.CharField(write_only=True, min_length=6)
    email = serializers.EmailField()

    class Meta:
        model = User
        fields = ["email", "password", "username"]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email already exists")
        return value.lower()

    @transaction.atomic
    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data.get("email", "").lower(),
            username=validated_data.get("username", validated_data["email"]),
            password=validated_data["password"],
            is_active=True
        )

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data.get("username"), password=data.get("password"))
        if not user:
            raise serializers.ValidationError("Username or password are invalid")
        if not user.is_active:
            raise serializers.ValidationError("Account has not been activated")
                    
        refresh = RefreshToken.for_user(user)
            
        return {
            "user_id": user.pk,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }

class TranslationRequestSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=255, trim_whitespace=True)
    language_pair_id = serializers.IntegerField()

    def validate_text(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("Word cannot be empty.")
        return value

class TranslationResponseSerializer(serializers.Serializer):
    text = serializers.CharField()
    corrected_text = serializers.CharField(
        allow_null=True,
    )
    translations = serializers.ListField(
        child=serializers.CharField(),
    )
    examples = serializers.ListField(
        child=serializers.CharField(),
    )

class FlashcardReviewRequestSerializer(serializers.Serializer):
    """Validates the body of POST /api/flashcards/{id}/review/."""
 
    result = serializers.ChoiceField(choices=["again", "hard", "good", "easy"])

class FlashcardStateSerializer(serializers.ModelSerializer):
    """
    Read-only view of a flashcard's scheduling state. Used both for the
    review endpoint's response and for the due-cards endpoint. This is
    deliberately separate from your main FlashcardSerializer (which
    presumably also exposes text/translations/examples/categories) so the
    scheduling endpoints stay lean - add fields here if your frontend needs
    more per-card detail in these two responses specifically.
    """
 
    class Meta:
        model = Flashcard
        fields = [
            "id",
            "text",
            "status",
            "ease_factor",
            "interval",
            "repetitions",
            "learning_step",
            "review_count",
            "next_review",
        ]
        read_only_fields = fields