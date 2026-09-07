from django.urls import path

from chorum_murohc.api.views import health

app_name = 'api_v1'

urlpatterns = [
    path('health/', health, name='health'),
]
