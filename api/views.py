import logging

from rest_framework.views import APIView
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status, viewsets, mixins
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.decorators import action
from rest_framework.throttling import UserRateThrottle
from django.shortcuts import get_object_or_404
from django.db.models import Count

from django.utils import timezone

from django.contrib.auth import get_user_model

from .throttles import TranslationThrottle

User = get_user_model()

from .models import (
    Category,
    UserProgress,
    Flashcard,
    LanguagePair
)

from .serializers import (
    LoginSerializer,
    RegisterSerializer,
    CategorySerializer,
    UserProgressSerializer,
    FlashcardSerializer,
    TranslationRequestSerializer,
    TranslationResponseSerializer,
    UserSerializer,
    LanguagePairSerializer,
    FlashcardReviewRequestSerializer,
    FlashcardStateSerializer
)

from api.services.deepseek_service import DeepSeekService
from .services.spaced_repetition import review_flashcard

logger = logging.getLogger(__name__)

class RegisterAPIView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "user": UserSerializer(user).data,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "message": "User registered successfully.",
            },
            status=status.HTTP_201_CREATED,
        )

class LoginAPIView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh_token")
        if not refresh_token:
            return Response({"detail": "Refresh token required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response(
                {"detail": "Invalid or blacklisted token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": "Logout successful"}, status=status.HTTP_200_OK)


class LanguagePairViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = LanguagePairSerializer

    def get_queryset(self):
        return LanguagePair.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class CategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CategorySerializer

    def get_queryset(self):
        qs = (
            Category.objects.filter(user=self.request.user)
            .annotate(card_count=Count("flashcards", distinct=True))
            .order_by("-updated_at")
        )
        language_pair_id = self.request.query_params.get("language_pair")
        if language_pair_id is not None:
            qs = qs.filter(language_pair_id=language_pair_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(
    detail=True,
    methods=["get"],
    url_path="flashcards",
    )
    def flashcards(self, request, pk=None):
        category = self.get_object()

        flashcards = category.flashcards.filter(
            user=request.user
        )

        serializer = FlashcardSerializer(
            flashcards,
            many=True,
        )

        return Response(serializer.data)

    @flashcards.mapping.post
    def create_flashcard(self, request, pk=None):
        category = self.get_object()

        serializer = FlashcardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        flashcard = serializer.save(
            user=request.user,
        )

        flashcard.categories.add(category)

        return Response(
            FlashcardSerializer(flashcard).data,
            status=status.HTTP_201_CREATED,
        )

class FlashcardViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = FlashcardSerializer

    def get_queryset(self):
        return Flashcard.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        flashcard = self.get_object()
 
        request_serializer = FlashcardReviewRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        result = request_serializer.validated_data["result"]
        UserProgress.objects.create(
            user=request.user,
            flashcard=flashcard,
            result=result,
            interval_before=flashcard.interval,
            ease_factor_before=flashcard.ease_factor,
            status_before=flashcard.status,
        )
 
        review_flashcard(flashcard, result)
 
        response_data = FlashcardStateSerializer(flashcard).data
        response_data["result"] = result
        return Response(response_data, status=status.HTTP_200_OK)
 
    @action(detail=False, methods=["get"], url_path="study")
    def study(self, request):
        category_id = request.query_params.get("category")
        card_type = request.query_params.get("type", "due")
        new_limit = int(request.query_params.get("new_limit", 20))

        if not category_id:
            return Response(
                {"detail": "Category is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if card_type not in ("new", "due"):
            return Response(
                {"detail": "Type must be 'new' or 'due'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        category = get_object_or_404(
            Category,
            id=category_id,
            user=request.user,
        )

        base_qs = self.get_queryset().filter(
            categories=category,
        )

        if card_type == "new":
            flashcards = (
                base_qs
                .filter(status="new")
                .order_by("created_at")[:new_limit]
            )

        else: 
            now = timezone.now()

            flashcards = (
                base_qs
                .filter(
                    next_review__isnull=False,
                    next_review__lte=now,
                )
                .order_by("next_review")
            )

        return Response(
            FlashcardSerializer(
                flashcards,
                many=True,
            ).data
        )


class TranslationPreviewAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [TranslationThrottle, UserRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = TranslationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_text = serializer.validated_data["text"]
        language_pair_id = serializer.validated_data["language_pair_id"]
        language_pair = get_object_or_404(LanguagePair, id=language_pair_id, user=request.user)
        service = DeepSeekService()
        result = service.translate(validated_text, language_pair)
        return Response(TranslationResponseSerializer(result).data, status=status.HTTP_200_OK)
        

        
