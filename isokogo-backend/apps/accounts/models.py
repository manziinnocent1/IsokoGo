from django.db import models

class User(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, unique=True)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    password = models.CharField(max_length=128)
    role = models.CharField(max_length=20, choices=[('admin', 'Admin'), ('user', 'User')], default='user')
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        
class UserVerification(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verifications')
    verification_type = models.CharField(max_length=30)
    verification_code_has = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_verifications'
        verbose_name = 'User Verification'
        verbose_name_plural = 'User Verifications'        