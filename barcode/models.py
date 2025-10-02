from django.db import models

class Bottle(models.Model):
    MATERIAL_CHOICES = [
        ('plastic', 'Plastic'),
        ('aluminium', 'Aluminium'),
    ]

    size = models.FloatField()
    name = models.CharField(max_length=250)
    image = models.ImageField(upload_to="bottle/images/")
    material = models.CharField(max_length=20, choices=MATERIAL_CHOICES)
    sku = models.CharField(max_length=16)

    def __str__(self):
        return f"{self.name} ({self.material})"
