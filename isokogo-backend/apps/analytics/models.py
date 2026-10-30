from django.db import models

class analytics(models.Model):
    id = models.CharField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    resolved_at = models.DateTimeField()
    
    class Meta:
                    db_table = 'analytics'
                    verbose_name = 'Analytics'
                    verbose_name_plural = 'Analytics'
