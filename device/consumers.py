from channels.generic.websocket import AsyncWebsocketConsumer
import json

class DeviceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.serial_number = self.scope['url_route']['kwargs']['serial_number']
        self.group_name = f"device_{self.serial_number}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f"✅ Device {self.serial_number} connected")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        print(f"❌ Device {self.serial_number} disconnected")

    async def session_created(self, event):
        await self.send(text_data=json.dumps({
            "event": "session_created",
            "data": event["message"]
        }))

    async def session_stopped(self, event):
        await self.send(text_data=json.dumps({
            "event": "session_stopped",
            "data": event["message"]
        }))


class SessionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.group_name = f"session_{self.session_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f"✅ Session {self.session_id} connected")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        print(f"❌ Session {self.session_id} disconnected")

    async def item_scanned(self, event):
        await self.send(text_data=json.dumps({
            "event": "item_scanned",
            "data": event["message"]
        }))