from rest_framework import serializers
from .models import Device, Session, SessionItem

class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = '__all__'


class SessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Session
        fields = '__all__'


class SessionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionItem
        fields = '__all__'