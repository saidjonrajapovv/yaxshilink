from django.urls import path
from .views import CreateNewsSessionAPIView, StopSessionAPIView, SessionDetailAPIView, SessionCreateItemAPIView

urlpatterns = [
    path('session/create/', CreateNewsSessionAPIView.as_view(), name='create_news_session'),
    path('session/stop/', StopSessionAPIView.as_view(), name='stop_session'),
    path('session/<int:session_id>/', SessionDetailAPIView.as_view(), name='get_session'),
    path('session/<int:session_id>/items/', SessionCreateItemAPIView.as_view(), name='create_session_item'),
]