from rest_framework import serializers
from .models import Bottle


class BarcodeSerializer(serializers.ModelSerializer):

    class Meta:
        model = Bottle
        fields = "__all__"
