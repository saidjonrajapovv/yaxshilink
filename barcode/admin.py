from django.contrib import admin
from .models import Bottle


@admin.register(Bottle)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "size", "sku", )
    search_fields = ("sku",'name')
