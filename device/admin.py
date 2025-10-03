from django.contrib import admin
from .models import Device, Session, SessionItem

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "serial_number", "location", "created_at")
    search_fields = ("name", "serial_number", "location")
    readonly_fields = ("created_at",)


class SessionItemInline(admin.TabularInline):
    model = SessionItem
    extra = 1

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    inlines = [SessionItemInline]
    list_display = ("id", "device", "phone_number", "status", "start_time", "end_time")
    search_fields = ("device__name", "phone_number")
    readonly_fields = ("start_time", "end_time")