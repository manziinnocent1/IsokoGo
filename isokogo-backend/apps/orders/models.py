from django.db import models

class order(models.Model):
    id = models.CharField()
    order_number = models.CharField()
    customer = models.ForeignKey()
    delivery_address = models.ForeignKey()
    delivery-address_snapshot = models.ForeignKey()
    status = models.CharField()
    subtotal = models.DecimalField()
    discount_amount = models.DecimalField()
    delivery_fee = models.DecimalField()
    tax_amount = models.DecimalField()
    total_amount = models.DecimalField()
    customer_notes = models.DecimalField()
    scheduled_delivery = models.DecimalField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    
    class Meta:
            db_table = 'orders'
            verbose_name = 'Orders'
            verbose_name_plural = 'Orders'

class OrderItem(models.Model):
    id = models.CharField()
    order = models.ForeignKey()
    product = models.ForeignKey()
    Variant = models.ForeignKey()
    product_name = models.CharField()
    variant_name = models.CharField()
    sku = models.CharField()
    quantity = models.DecimalField()
    unit_price = models.DecimalField()
    subtotal = models.DecimalField()
    
    class Meta:
                db_table = 'orders item'
                verbose_name = 'Orders Item'
                verbose_name_plural = 'Orders Item'
    

class OrderStatusHistory(models.Model):
    id = models.CharField()
    order = models.ForeignKey()
    previous_status = models.CharField()
    new_status = models.CharField()
    changed_by = models.ForeignKey()
    note = models.TextField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    
    class Meta:
                    db_table = 'order status history'
                    verbose_name = 'Order Status History'
                    verbose_name_plural = 'Order Status History'
 
class OrderSubstitution(models.Model):
    id = models.CharField()
    order_item = models.ForeignKey()
    requested_variant = models.ForeignKey()
    suggested_variant = models.ForeignKey()
    status = models.CharField()
    customer_response = models.TextField()
    created_at = models.DateTimeField()
    
    class Meta:
                 db_table = 'Order substitution'
                 verbose_name = 'Order Substitution'
                 verbose_name_plural = 'Order Substitution'
    
    
        
    