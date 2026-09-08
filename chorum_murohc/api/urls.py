from django.urls import path

from chorum_murohc.api.chores import (
    ChoreDeactivateView,
    ChoreDetailView,
    ChoreListView,
    ChoreReactivateView,
)
from chorum_murohc.api.session import LoginView, LogoutView, SessionView
from chorum_murohc.api.views import health

app_name = 'api_v1'

urlpatterns = [
    path('health/', health, name='health'),
    path('auth/session/', SessionView.as_view(), name='auth-session'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('chores/', ChoreListView.as_view(), name='chore-list'),
    path('chores/<int:pk>/', ChoreDetailView.as_view(), name='chore-detail'),
    path(
        'chores/<int:pk>/deactivate/',
        ChoreDeactivateView.as_view(),
        name='chore-deactivate',
    ),
    path(
        'chores/<int:pk>/reactivate/',
        ChoreReactivateView.as_view(),
        name='chore-reactivate',
    ),
]
