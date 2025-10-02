from django.db import models


class Order(models.Model):
    phone_number = models.CharField(max_length=20)  # 250 emas, real formatga mos
    
    def __str__(self):
        return f"Order #{self.id} - {self.phone_number}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    sku = models.CharField(max_length=100)  # Product SKU (yoki boshqa modelga FK)
    
    def __str__(self):
        return f"{self.sku} (Order #{self.order.id})"
