import threading
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


def schedule_session_auto_close(session):
    def check_and_close():
        threading.Timer(60, perform_check).start()

    def perform_check():
        from .models import Session
        try:
            refreshed = Session.objects.get(id=session.id)
            if refreshed.status == 'active' and (timezone.now() - refreshed.last_activity).total_seconds() >= 60:
                refreshed.status = 'inactive'
                refreshed.end_time = timezone.now()
                refreshed.save(update_fields=['status', 'end_time'])

                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"session_{refreshed.id}",
                    {
                        "type": "session.stopped",
                        "message": {
                            "session_id": refreshed.id,
                            "status": refreshed.status,
                            "reason": "timeout",
                        },
                    }
                )
                async_to_sync(channel_layer.group_send)(
                    f"device_{refreshed.device.serial_number}",
                    {
                        "type": "session.stopped",
                        "message": {
                            "session_id": refreshed.id,
                            "phone_number": refreshed.phone_number,
                            "device": refreshed.device.name,
                            "status": refreshed.status,
                            "reason": "timeout",
                        },
                    }
                )
        except Session.DoesNotExist:
            pass

    check_and_close()
