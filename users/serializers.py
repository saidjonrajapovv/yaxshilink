from rest_framework import serializers

class SendCodeSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)


class VerifyCodeSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)
    code = serializers.CharField(max_length=6)
