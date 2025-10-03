from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from .views import SendCodeAPIView, VerifyCodeAPIView, AuthCheckAPIView

urlpatterns = [
    path('auth/send-code/', SendCodeAPIView.as_view(), name='send_code'),
    path('auth/verify-code/', VerifyCodeAPIView.as_view(), name='verify_code'),
    
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('auth/check/', AuthCheckAPIView.as_view(), name='auth_check'),
]
