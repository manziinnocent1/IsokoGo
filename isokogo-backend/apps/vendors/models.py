from django.db import models

class Vendor(models.Model):
    id = models.AutoField(primary_key=True)
    owner = models.OneToOneField('accounts.User', on_delete=models.CASCADE, related_name='vendor_profile')
    businness_name = models.CharField(max_length=100)
    businness_description = models.TextField()
    contact_phone = models.CharField(max_length=15)
    contact_email = models.EmailField()
    businness_address = models.TextField()
    business_logo = models.ImageField(upload_to='business_logos/', null=True, blank=True)
    business_registration_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('suspended', 'Suspended')], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vendors'
        verbose_name = 'Vendor'
        verbose_name_plural = 'Vendors'

class VendorDocument(models.Model):
    id = models.AutoField(primary_key=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50)
    document_file = models.FileField(upload_to='vendor_documents/')
    verification_status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vendor_documents'
        verbose_name = 'Vendor Document'
        verbose_name_plural = 'Vendor Documents'