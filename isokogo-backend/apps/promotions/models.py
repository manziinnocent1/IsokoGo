from django.db import models

class Coupon(models.Model):
    id = models.CharField()
    code = models.CharField()
    description = models.TextField()
    discount_type = models.Choices()
    discount_value = models.DecimalField()
    minimum_order_amount = models.DecimalField()
    maximum_discount = models.DecimalField()
    usage_limit = models.PositiveIntegerField()
    usage_per_customer = models.PositiveIntegerField()
    start_date = models.DateTimeField()
    expiry_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    
    class Meta:
            db_table = 'coupon'
            verbose_name = 'Coupon'
            verbose_name_plural = 'Coupon'
    
class CouponUsage(models.Model):
    id = models.CharField()
    coupon = models.ForeignKey()
    customer = models.ForeignKey()
    order = models.ForeignKey()
    used_at = models.DateTimeField
    
    class Meta:
                db_table = 'couponusage'
                verbose_name = 'Coupon Usage'
                verbose_name_plural = 'Coupon Usage'

class Promotion(models.Model):
    id = models.CharField()
    name = models.CharField()
    description = models.TextField()
    banner_image = models.ImageField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    
    class Meta:
                db_table = 'promotion'
                verbose_name = 'Promotion'
                verbose_name_plural = 'Promotion'  
