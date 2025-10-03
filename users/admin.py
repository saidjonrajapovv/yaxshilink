from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, SMSCode

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    fieldsets = UserAdmin.fieldsets + (
        ("Additional Info", {"fields": ("phone_number",)}),
    )
    list_display = ("username", "email", "first_name", "last_name", "phone_number", "is_staff")


@admin.register(SMSCode)
class SMSCodeAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "code", "created_at")
    list_filter = ("created_at",)
    search_fields = ("phone_number", "code")