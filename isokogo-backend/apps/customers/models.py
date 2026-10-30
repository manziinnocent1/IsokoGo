from django.db import models

class CustomerProfile(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField('accounts.User', on_delete=models.CASCADE, related_name='customer_profile')
    profile_image = models.ImageField(upload_to='profile_images/', null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    preferred_language = models.CharField(max_length=30, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customer_profiles'
        verbose_name = 'Customer Profile'
        verbose_name_plural = 'Customer Profiles'

class CustomerAdress(models.Model):
    id = models.AutoField(primary_key=True)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='addresses')
    address_name = models.CharField(max_length=100)
    recepient_name = models.CharField(max_length=100)
    recepient_phone_number = models.CharField(max_length=15)
    province = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    sector = models.CharField(max_length=100)
    cell = models.CharField(max_length=100)
    village = models.CharField(max_length=100)
    street_address = models.CharField(max_length=255)
    delivery_instructions = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'customer_addresses'
        verbose_name = 'Customer Address'
        verbose_name_plural = 'Customer Addresses'
        