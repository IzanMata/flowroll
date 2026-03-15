from django.db import models


class Belt(models.Model):

    class BeltColor(models.TextChoices):
        WHITE = "white", "White"
        BLUE = "blue", "Blue"
        PURPLE = "purple", "Purple"
        BROWN = "brown", "Brown"
        BLACK = "black", "Black"

    color = models.CharField(max_length=20, choices=BeltColor.choices, unique=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(
        help_text="Belt progression order, 1=white, 5=black"
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.get_color_display()
