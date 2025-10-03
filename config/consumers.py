from channels.generic.websocket import AsyncWebsocketConsumer
import json

class DeviceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.device_id = self.scope['url_route']['kwargs']['device_id']
        self.group_name = f"device_{self.device_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        print(f"✅ Device {self.device_id} connected")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        print(f"❌ Device {self.device_id} disconnected")

    async def receive(self, text_data):
        data = json.loads(text_data)
        print(f"📩 From {self.device_id}: {data}")

        await self.send(text_data=json.dumps({
            "status": "received",
            "echo": data
        }))
