from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import SendCodeSerializer, VerifyCodeSerializer
from django.contrib.auth import get_user_model
import random
from django.utils import timezone
from .models import SMSCode
from rest_framework.permissions import IsAuthenticated

User = get_user_model()

def generate_sms_code():
    return str(random.randint(100000, 999999))


class SendCodeAPIView(APIView):
    def post(self, request):
        serializer = SendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']

        # Generate and store code
        code = generate_sms_code()
        SMSCode.objects.create(phone_number=phone_number, code=code)

        # TODO: integrate real SMS gateway (Eskiz, Twilio, etc.)
        print(f"📲 [DEBUG] SMS code for {phone_number}: {code}")

        return Response({"success": True, "message": "SMS code sent."}, status=status.HTTP_200_OK)


class VerifyCodeAPIView(APIView):
    def post(self, request):
        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data['phone_number']
        code = serializer.validated_data['code']

        try:
            sms_record = SMSCode.objects.filter(phone_number=phone_number).latest('created_at')
        except SMSCode.DoesNotExist:
            return Response({"success": False, "error": "Code not found."}, status=status.HTTP_400_BAD_REQUEST)

        if sms_record.is_expired():
            return Response({"success": False, "error": "Code expired."}, status=status.HTTP_400_BAD_REQUEST)

        if sms_record.code != code:
            return Response({"success": False, "error": "Invalid code."}, status=status.HTTP_400_BAD_REQUEST)

        # Get or create user
        user, created = User.objects.get_or_create(phone_number=phone_number, defaults={"username": phone_number})

        # Generate tokens
        refresh = RefreshToken.for_user(user)
        tokens = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }

        return Response({
            "success": True,
            "is_new_user": created,
            "user": {
                "id": user.id,
                "phone_number": user.phone_number,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            "tokens": tokens
        }, status=status.HTTP_200_OK)


class AuthCheckAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "success": True,
            "user": {
                "id": user.id,
                "phone_number": getattr(user, "phone_number", None),
                "first_name": user.first_name,
                "last_name": user.last_name,
            }
        }, status=status.HTTP_200_OK)
