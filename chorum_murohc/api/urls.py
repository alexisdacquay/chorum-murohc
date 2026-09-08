from django.urls import path

from chorum_murohc.api.audit import AuditEventListView
from chorum_murohc.api.balances import BalanceView, LedgerHistoryView
from chorum_murohc.api.chores import (
    ChoreDeactivateView,
    ChoreDetailView,
    ChoreListView,
    ChoreReactivateView,
)
from chorum_murohc.api.members import (
    MemberDeactivateView,
    MemberDetailView,
    MemberListView,
    MemberReactivateView,
)
from chorum_murohc.api.session import LoginView, LogoutView, SessionView
from chorum_murohc.api.submissions import SubmissionListView
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
    path('submissions/', SubmissionListView.as_view(), name='submission-list'),
    path('household-members/', MemberListView.as_view(), name='member-list'),
    path(
        'household-members/<int:pk>/',
        MemberDetailView.as_view(),
        name='member-detail',
    ),
    path(
        'household-members/<int:pk>/deactivate/',
        MemberDeactivateView.as_view(),
        name='member-deactivate',
    ),
    path(
        'household-members/<int:pk>/reactivate/',
        MemberReactivateView.as_view(),
        name='member-reactivate',
    ),
    path('audit/', AuditEventListView.as_view(), name='audit-list'),
    path('balance/', BalanceView.as_view(), name='balance'),
    path('ledger/', LedgerHistoryView.as_view(), name='ledger-history'),
]
