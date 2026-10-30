from django.db import models

class Cart(models.Model):
    id = models.CharField()
    customer = models.ForeignKey()
    status = models.Choices('ACTIVE', 'CONVERTED', 'ABONDONED')
    created_at = models.DateTimeField()
    Updated_at = models.DateTimeField()
    
    class Meta:
            db_table = 'cart'
            verbose_name = 'Cart'
            verbose_name_plural = 'Cart'
    
class CartItem(models.Model):
    id = models.CharField()
    cart = models.ForeignKey()
    variant = models.ForeignKey()
    quantity = models.DecimalField()
    added_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    
    class Meta:
                db_table = 'cart item'
                verbose_name = 'Cart Item'
                verbose_name_plural = 'Cart Item'
    
