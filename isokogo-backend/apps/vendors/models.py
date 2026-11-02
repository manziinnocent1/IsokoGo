
import uuid

from django.db import models
from django.conf import settings
from django.core.validators import MinLengthValidator


class Vendor(models.Model):

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        SUSPENDED = 'suspended', 'Suspended'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='vendor_profile'
    )

    business_name = models.CharField(
        max_length=150
    )

    business_description = models.TextField(
        blank=True,
        null=True
    )

    contact_phone = models.CharField(
        max_length=15
    )

    contact_email = models.EmailField()

    business_address = models.TextField()

    business_logo = models.ImageField(
        upload_to='vendors/logos/',
        null=True,
        blank=True
    )

    business_registration_number = models.CharField(
        max_length=100,
        unique=True
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    rejection_reason = models.TextField(
        blank=True,
        null=True
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vendors'
        verbose_name = 'Vendor'
        verbose_name_plural = 'Vendors'
        ordering = ['-created_at']

        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['business_name']),
        ]

    def __str__(self):
        return self.business_name


class VendorDocument(models.Model):

    class DocumentType(models.TextChoices):
        BUSINESS_REGISTRATION = (
            'business_registration',
            'Business Registration Certificate'
        )
        TAX_CERTIFICATE = 'tax_certificate', 'Tax Certificate'
        NATIONAL_ID = 'national_id', 'National ID'
        PROOF_OF_ADDRESS = 'proof_of_address', 'Proof of Address'
        OTHER = 'other', 'Other'

    class VerificationStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name='documents'
    )

    document_type = models.CharField(
        max_length=50,
        choices=DocumentType.choices
    )

    document_file = models.FileField(
        upload_to='vendors/documents/'
    )

    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING
    )

    rejection_reason = models.TextField(
        blank=True,
        null=True
    )

    verified_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vendor_documents'
        verbose_name = 'Vendor Document'
        verbose_name_plural = 'Vendor Documents'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.vendor.business_name} - {self.document_type}"
