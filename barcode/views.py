from rest_framework import viewsets
from .models import Bottle
from .serializers import BarcodeSerializer


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Bottle.objects.all()
    serializer_class = BarcodeSerializer

