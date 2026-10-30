from django.db import models

class Notification(models.Model):
    id = models.CharField()
    recipient = models.ForeignKey()
    title = models.CharField()
    message = models.TextField()
    notification_type = models.Choices()
    is_read = models.BooleanField(default=True)
    related_order = models.ForeignKey()
    created_at = models.DateTimeField()
    
    class Meta:
            db_table = 'notifications'
            verbose_name = 'Notification'
            verbose_name_plural = 'Notification'
        
