from django.urls import re_path
from device import consumers

websocket_urlpatterns = [
    re_path(r"^ws/device/(?P<serial_number>[-\w]+)/$", consumers.DeviceConsumer.as_asgi()),
    re_path(r"^ws/session/(?P<session_id>\d+)/$", consumers.SessionConsumer.as_asgi()),
]
