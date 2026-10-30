from django.db import models

class SupportTicket(models.Model):
   id = models.CharField()
   customer = models.ForeignKey()
   order = models.ForeignKey()
   subject = models.CharField()
   description = models.TextField()
   priority = models.Choices()
   status = models.Choices()
   assigned_to = models.ForeignKey()
   created_at = models.DateTimeField()
   resolved_at = models.DateTimeField() 
   
   class Meta:
           db_table = 'support tickets'
           verbose_name = 'Support Tickets'
           verbose_name_plural = 'Support Tickets'
