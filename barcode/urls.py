from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BarcodeViewSet, CheckBottleAPIView

router = DefaultRouter()
router.register(r'bottles', BarcodeViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('bottle/check/', CheckBottleAPIView.as_view(), name='check-bottle'),
]
