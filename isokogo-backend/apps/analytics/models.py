import uuid

from django.db import models


class Analytics(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        db_table = "analytics"
        verbose_name = "Analytics"
        verbose_name_plural = "Analytics"
        ordering = ["-created_at"]

    def __str__(self):
        return str(self.id)