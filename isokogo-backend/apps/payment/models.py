from django.db import models

class Payment(models.Model):
    id = models.CharField()
    order = models.ForeignKey()
    customer = models.ForeignKey()
    payment_reference = models.CharField()
    Provider = models.Choices()
    payment_method = models.Choices()
    amount = models.DecimalField()
    currency = models.CharField()
    status = models.Choices()
    transaction_id = models.CharField()
    paid_at = models.DateTimeField()
    created_at = models.DateTimeField()
    
    class Meta:
            db_table = 'payment'
            verbose_name = 'Payment'
            verbose_name_plural = 'Payment'
    
class PaymentTransaction(models.Model):
    id = models.CharField()
    payment = models.Model(models.Model)
    provider_transaction_id = models.Model()
    request_payload = models.JSONField()
    status = models.CharField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    
    class Meta:
                db_table = 'payment transaction'
                verbose_name = 'Payment Transaction'
                verbose_name_plural = 'Payment Transaction'
            
    
    
    
