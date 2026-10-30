from django.db import models

class Warehouse(models.Model):
    id = models.CharField()
    name = models.CharField()
    address = models.TextField()
    contact_phone = models.CharField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    
    class Meta:
            db_table = 'warehouse'
            verbose_name = 'Warehouse'
            verbose_name_plural = 'Warehouse'

class Stock(models.Model):
    id = models.CharField()
    variant = models.ForeignKey()
    warehouse = models.ForeignKey()
    quantity_on_hand = models.DecimalField()
    quantity_reserved = models.DecimalField()
    reorder_level = models.DecimalField()
    updated_at = models.DecimalField()
    
    class Meta:
                db_table = 'stock'
                verbose_name = 'Stock'
                verbose_name_plural = 'Stock'
                
class StockMovement(models.Model):
    id = models.CharField()
    stock = models.ForeignKey("app.Model", verbose_name=(""), on_delete=models.CASCADE)
    movement_type = models.CharField('PURCHASE', 'SALE', 'RETURN', 'ADJUSTMENT', 'DAMAGE', 'EXPIRY', 'TRANSFER')
    quantity = models.DecimalField()
    reference = models.CharField()
    reason = models.TextField()
    performed_by = models.ForeignKey()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()  
    
    class Meta:
                db_table = 'stock movement'
                verbose_name = 'Stock Movement'
                verbose_name_plural = 'Stock Movement'   
                    
class Supplier(models.Model):
    id = models.CharField()
    name = models.CharField()
    contact_person = models.CharField()
    email = models.EmailField()
    address = models.TextField()
    is_active = models.BooleanField(default=True) 
    
    class Meta:
                 db_table = 'supplier'
                 verbose_name = 'Supplier'
                 verbose_name_plural = 'Supplier' 
                 
class PurchaseOrder(models.Model):
    id = models.CharField()
    supplier = models.ForeignKey()
    warehouse = models.ForeignKey()
    reference_number = models.CharField()
    status = models.ChoiceField()
    total_amount = models.DecimalField()
    expected_delivery = models.DateField()
    created_by = models.ForeignKey()
    Created_at = models.DateTimeField()
    Updated_at = models.DateTimeField()
    
    class Meta:
                db_table = 'purchase order'
                verbose_name = 'Purchase Order'
                verbose_name_plural = 'Purchase Order'
                
class PurchaseOrderItem(models.Model):
    id = models.CharField()
    purchase_order = models.ForeignKey()
    variant = models.ForeignKey()
    quantity = models.DecimalField()
    unit_cost = models.DecimalField()
    subtotal = models.DecimalField()
    
    class Meta:
                    db_table = 'purchase order item'
                    verbose_name = 'Purchase Order Item'
                    verbose_name_plural = 'Purchase Order Item'
    
                                               