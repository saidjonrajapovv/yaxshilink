from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Bottle
from .serializers import BarcodeSerializer


class BarcodeViewSet(viewsets.ModelViewSet):
    queryset = Bottle.objects.all()
    serializer_class = BarcodeSerializer

class CheckBottleAPIView(APIView):
    def post(self, request, format=None):
        sku = request.data.get('sku')
        try:
            bottle = Bottle.objects.get(sku=sku)
            material = bottle.material
            return Response({'exists': True, 'bottle': BarcodeSerializer(bottle).data, 'material': material})
        except Bottle.DoesNotExist:
            return Response({'exists': False, "material": "R"})