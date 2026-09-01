from unittest import mock
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import User, UserProgress, Flashcard

class TestStatsViews(APITestCase):
    
    def setUp(self):
        self.user = User.objects.create(username="testuser")
        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_access(self):
        self.client.force_authenticate(user=None)
        url = reverse('stats-overview')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_parse_int_query_param_valid(self):
        url = reverse('stats-difficult-cards')
        response = self.client.get(url, {'limit': 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_parse_int_query_param_invalid_raises_400(self):
        url = reverse('stats-difficult-cards')
        response = self.client.get(url, {'limit': 'abc'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('limit', response.data)

    def test_category_stats_requires_language_pair(self):
        url = reverse('stats-categories')
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], "language_pair is required.")

        response = self.client.get(url, {'language_pair': 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_progress_viewset_limit_and_filter(self):
        card = Flashcard.objects.create(user=self.user, text="Hablar")
        for _ in range(3):
            UserProgress.objects.create(
                user=self.user, 
                flashcard=card, 
                result="good",
                ease_factor_before=2.5,
                interval_before=0.0,
                status_before="new"
            )
            
        try:
            url = reverse('userprogress-list') 
        except Exception:
            url = '/api/progress/' 
        
        # Тестируем limit
        response = self.client.get(url, {'limit': 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data['results'] if 'results' in response.data else response.data
        self.assertEqual(len(data), 2)
        
        # Тестируем фильтр
        response = self.client.get(url, {'flashcard': card.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
    # ИЗМЕНЕНИЕ ЗДЕСЬ: правильный путь к stats_service
    @mock.patch('api.stats_views.stats_service.get_accuracy_trend')
    def test_accuracy_trend_bounds(self, mock_service):
        mock_service.return_value = []
        url = reverse('stats-trend')
        
        self.client.get(url, {'days': 150})
        mock_service.assert_called_with(self.user, None, 90)

        self.client.get(url, {'days': -5})
        mock_service.assert_called_with(self.user, None, 1)

    # ИЗМЕНЕНИЕ ЗДЕСЬ: правильный путь к stats_service
    @mock.patch('api.stats_views.stats_service.get_overview')
    def test_overview_with_language_pair(self, mock_service):
        mock_service.return_value = {}
        url = reverse('stats-overview')
        
        self.client.get(url, {'language_pair': 10})
        mock_service.assert_called_with(self.user, 10)