from django.utils import timezone
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


def generate_unique_serial_number():
    import uuid
    return str(uuid.uuid4())

def generate_device_token():
    import uuid
    return uuid.uuid4().hex 

class Device(models.Model):
    name = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=100, unique=True, default=generate_unique_serial_number)
    location = models.CharField(max_length=100)
    token = models.CharField(max_length=64, unique=True, default=generate_device_token)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.serial_number})"


class Session(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=[('active', 'Active'), ('inactive', 'Inactive')], default="active")
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(auto_now_add=True)

    def update_activity(self):
        self.last_activity = timezone.now()
        self.save(update_fields=['last_activity'])

    def __str__(self):
        return f"Session for {self.device.name} by {self.phone_number} starting at {self.start_time}"
    


class SessionItem(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='items')
    sku = models.CharField(max_length=16)
    timestamp = models.DateTimeField(auto_now_add=True)
    score = models.IntegerField(default=0)

    def __str__(self):
        return f"Item for session {self.session.id} at {self.timestamp}"