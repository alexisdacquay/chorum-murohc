from django.urls import path

from chorum_murohc.api.audit import AuditEventListView
from chorum_murohc.api.balances import BalanceView, LedgerHistoryView
from chorum_murohc.api.chores import (
    ChoreDeactivateView,
    ChoreDetailView,
    ChoreListView,
    ChoreReactivateView,
)
from chorum_murohc.api.creatures import CreatureLineListView, CreatureView
from chorum_murohc.api.members import (
    MemberDeactivateView,
    MemberDetailView,
    MemberListView,
    MemberPasswordResetView,
    MemberReactivateView,
)
from chorum_murohc.api.overview import OverviewView
from chorum_murohc.api.password import PasswordChangeView
from chorum_murohc.api.pin import PinView
from chorum_murohc.api.progression import ProgressionAcknowledgeView, ProgressionView
from chorum_murohc.api.redemptions import (
    RedemptionCancelView,
    RedemptionFulfilView,
    RedemptionListView,
)
from chorum_murohc.api.rewards import (
    RewardDeactivateView,
    RewardDetailView,
    RewardListView,
    RewardReactivateView,
)
from chorum_murohc.api.session import (
    HouseholdSwitchView,
    LoginView,
    LogoutView,
    SessionView,
)
from chorum_murohc.api.submissions import (
    ApprovingParentListView,
    PendingApprovalListView,
    SubmissionDecisionView,
    SubmissionListView,
)
from chorum_murohc.api.views import health

app_name = 'api_v1'

urlpatterns = [
    path('health/', health, name='health'),
    path('auth/session/', SessionView.as_view(), name='auth-session'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/household/', HouseholdSwitchView.as_view(), name='auth-household'),
    path('auth/pin/', PinView.as_view(), name='auth-pin'),
    path('auth/password/', PasswordChangeView.as_view(), name='auth-password'),
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
    path(
        'submissions/<int:pk>/decide/',
        SubmissionDecisionView.as_view(),
        name='submission-decide',
    ),
    path('approvals/', PendingApprovalListView.as_view(), name='approval-list'),
    path(
        'approving-parents/',
        ApprovingParentListView.as_view(),
        name='approving-parent-list',
    ),
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
    path(
        'household-members/<int:pk>/reset-password/',
        MemberPasswordResetView.as_view(),
        name='member-reset-password',
    ),
    path('audit/', AuditEventListView.as_view(), name='audit-list'),
    path('overview/', OverviewView.as_view(), name='overview'),
    path('balance/', BalanceView.as_view(), name='balance'),
    path('ledger/', LedgerHistoryView.as_view(), name='ledger-history'),
    path('rewards/', RewardListView.as_view(), name='reward-list'),
    path('rewards/<int:pk>/', RewardDetailView.as_view(), name='reward-detail'),
    path(
        'rewards/<int:pk>/deactivate/',
        RewardDeactivateView.as_view(),
        name='reward-deactivate',
    ),
    path(
        'rewards/<int:pk>/reactivate/',
        RewardReactivateView.as_view(),
        name='reward-reactivate',
    ),
    path('redemptions/', RedemptionListView.as_view(), name='redemption-list'),
    path(
        'redemptions/<int:pk>/fulfil/',
        RedemptionFulfilView.as_view(),
        name='redemption-fulfil',
    ),
    path(
        'redemptions/<int:pk>/cancel/',
        RedemptionCancelView.as_view(),
        name='redemption-cancel',
    ),
    path('creature/', CreatureView.as_view(), name='creature'),
    path(
        'creature/lines/',
        CreatureLineListView.as_view(),
        name='creature-line-list',
    ),
    path('progression/', ProgressionView.as_view(), name='progression'),
    path(
        'progression/acknowledge/',
        ProgressionAcknowledgeView.as_view(),
        name='progression-acknowledge',
    ),
]
