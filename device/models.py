from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


def generate_unique_serial_number():
    import uuid
    return str(uuid.uuid4())


class Device(models.Model):
    name = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=100, unique=True, default=generate_unique_serial_number)
    location = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.serial_number})"


class Session(models.Model):
    device = models.OneToOneField(Device, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=100)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Session for {self.device.name} by {self.phone_number} starting at {self.start_time}"


@receiver(post_save, sender=Device)
def create_session_for_device(sender, instance, created, **kwargs):
    if created:
        Session.objects.get_or_create(device=instance, defaults={"phone_number": ""})
