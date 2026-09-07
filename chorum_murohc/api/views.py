from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    renderer_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response


@api_view(['GET', 'HEAD'])
@authentication_classes([])
@permission_classes([AllowAny])
@renderer_classes([JSONRenderer])
def health(request):
    return Response({'status': 'ok'})
