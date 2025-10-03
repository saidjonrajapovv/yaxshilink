from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Device, Session
from .serializers import SessionItemSerializer
from django.utils import timezone
from .utils import schedule_session_auto_close

class CreateNewsSessionAPIView(APIView):
    def post(self, request, format=None):
        serial_number = request.data.get('serial_number')
        phone_number = request.data.get('phone_number')

        try:
            device = Device.objects.get(serial_number=serial_number)
            session = Session.objects.create(device=device, phone_number=phone_number)

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"device_{device.serial_number}",
                {
                    "type": "session.created",
                    "message": {
                        "session_id": session.id,
                        "phone_number": phone_number,
                        "device": device.name,
                        "status": session.status,
                    },
                }
            )

            return Response({'success': True, 'session_id': session.id})

        except Device.DoesNotExist:
            return Response({'success': False, 'error': 'Device not found'}, status=404)


class StopSessionAPIView(APIView):
    def post(self, request, format=None):
        session_id = request.data.get('session_id')

        try:
            session = Session.objects.get(id=session_id)

            if session.status == 'inactive':
                return Response({'success': False, 'error': 'Session already inactive'}, status=409)

            session.end_time = timezone.now()
            session.status = 'inactive'
            session.save()

            channel_layer = get_channel_layer()

            async_to_sync(channel_layer.group_send)(
                f"device_{session.device.serial_number}",
                {
                    "type": "session.stopped",
                    "message": {
                        "session_id": session.id,
                        "phone_number": session.phone_number,
                        "device": session.device.name,
                        "status": session.status,
                    },
                }
            )

            async_to_sync(channel_layer.group_send)(
                f"session_{session.id}",
                {
                    "type": "session.stopped",
                    "message": {
                        "session_id": session.id,
                        "status": session.status,
                    },
                }
            )

            return Response({'success': True})

        except Session.DoesNotExist:
            return Response({'success': False, 'error': 'Session not found'}, status=404)
        


class SessionDetailAPIView(APIView):
    def get(self, request, session_id, format=None):
        try:
            session = Session.objects.get(id=session_id)
            items = session.items.all().values('sku', 'timestamp', 'score')
            session_data = {
                'session_id': session.id,
                'device': session.device.name,
                'phone_number': session.phone_number,
                'status': session.status,
                'start_time': session.start_time,
                'end_time': session.end_time,
                'items': list(items),
            }
            return Response({'success': True, 'session': session_data})

        except Session.DoesNotExist:
            return Response({'success': False, 'error': 'Session not found'}, status=404)
        
class SessionCreateItemAPIView(APIView):
    def post(self, request, session_id, format=None):
        sku = request.data.get('sku')

        try:
            session = Session.objects.get(id=session_id)

            if session.status != 'active':
                return Response({'success': False, 'error': 'Session is inactive'}, status=409)

            item = session.items.create(sku=sku)

            items_data = SessionItemSerializer(session.items.all(), many=True).data

            session.update_activity()  
            schedule_session_auto_close(session)

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"session_{session.id}",
                {
                    "type": "item.scanned",
                    "message": {
                        "session_id": session.id,
                        "items": items_data,
                        "total_items": len(items_data),
                    },
                }
            )

            return Response({
                'success': True,
                'item_id': item.id,
                'session_id': session.id
            })

        except Session.DoesNotExist:
            return Response({'success': False, 'error': 'Session not found'}, status=404)