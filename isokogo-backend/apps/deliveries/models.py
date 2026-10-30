from django.db import models

class DeliveryPersonnel(models.Model):
    id = models.CharField()
    user = models.OneToOneField()
    vehicle_type = models.Choices()
    vehicle_registration = models.CharField()
    availability_status = models.Choices()
    is_verified = models.BooleanField(default=True)
    
    class Meta:
                db_table = 'delivery personnel'
                verbose_name = 'Delivery Personnel'
                verbose_name_plural = 'Delivery Personnel'
    
class DeliveryZone(models.Model):
    id = models.CharField()
    name = models.CharField()
    province = models.CharField()
    district = models.CharField()
    base_delivery_fee = models.DecimalField()
    estimated_delivery_minutes = models.PositiveIntegerField()
    is_active = models.BooleanField()
    
    class Meta:
                db_table = 'delivery zone'
                verbose_name = 'Delivery Zone'
                verbose_name_plural = 'Delivery Zone'  

class Delivery(models.Model):
    id = models.CharField()
    order = models.OneToOneField()
    delivery_personnel = models.ForeignKey()
    delivery_zone = models.ForeignKey()
    status = models.Choices()
    assigned_at = models.DateTimeField()
    picked_up_at = models.DateTimeField()
    delivered_at = models.DateTimeField()
    delivery_fee = models.DecimalField()
    recipient_name = models.CharField()
    recipient_phone = models.CharField()
    proof_of_delivery = models.ImageField()
    delivery_notes = models.TextField()
    delivery_status = models.Choices('PENDING_ASSIGNMENT', 'ASSIGNED', 'PICKED_UP', 'IN_TRANSIT', 'DELIVERED', 'FAILED')
    
    class Meta:
                db_table = 'delivery'
                verbose_name = 'Delivery'
                verbose_name_plural = 'Delivery'

class DeliveryTracking(models.Model):
    id = models.CharField()
    delivery = models.ForeignKey()
    recorded_at = models.DateTimeField()
    
    class Meta:
                db_table = 'delivery tracking'
                verbose_name = 'Delivery Tracking'
                verbose_name_plural = 'Delivery Tracking'
    