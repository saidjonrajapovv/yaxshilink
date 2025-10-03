from django.contrib import admin
from .models import Device

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "serial_number", "location", "created_at")
    search_fields = ("name", "serial_number", "location")
    readonly_fields = ("created_at",)