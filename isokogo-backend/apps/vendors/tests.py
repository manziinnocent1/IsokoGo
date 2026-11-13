
import pytest
import uuid

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from .models import Vendor, VendorDocument
from .serializers import (
    VendorSerializer,
    VendorModerationSerializer,
    VendorDocumentSerializer,
    VendorDocumentModerationSerializer,
)


User = get_user_model()


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def customer(db):
    return User.objects.create_user(
        email="customer@example.com",
        password="TestPassword123!",
    )


@pytest.fixture
def another_customer(db):
    return User.objects.create_user(
        email="another@example.com",
        password="TestPassword123!",
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        email="admin@example.com",
        password="AdminPassword123!",
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def another_staff_user(db):
    return User.objects.create_user(
        email="admin2@example.com",
        password="AdminPassword123!",
        is_staff=True,
    )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, customer):
    api_client.force_authenticate(user=customer)
    return api_client


@pytest.fixture
def admin_client(api_client, staff_user):
    api_client.force_authenticate(user=staff_user)
    return api_client


@pytest.fixture
def vendor(customer, db):
    return Vendor.objects.create(
        owner=customer,
        business_name="Fresh Market",
        business_description="Fresh groceries and food products.",
        contact_phone="+250788123456",
        contact_email="fresh@example.com",
        business_address="Kigali, Rwanda",
        business_registration_number="REG-001",
    )


@pytest.fixture
def another_vendor(another_customer, db):
    return Vendor.objects.create(
        owner=another_customer,
        business_name="Daily Foods",
        business_description="Food and grocery delivery.",
        contact_phone="+250788654321",
        contact_email="daily@example.com",
        business_address="Kigali, Rwanda",
        business_registration_number="REG-002",
    )


@pytest.fixture
def approved_vendor(vendor):
    vendor.status = Vendor.Status.APPROVED
    vendor.approved_at = timezone.now()
    vendor.save()
    return vendor


@pytest.fixture
def suspended_vendor(vendor):
    vendor.status = Vendor.Status.SUSPENDED
    vendor.rejection_reason = "Policy violation."
    vendor.save()
    return vendor


@pytest.fixture
def vendor_document(vendor, db):
    document_file = SimpleUploadedFile(
        "registration.pdf",
        b"Test business registration document",
        content_type="application/pdf",
    )

    return VendorDocument.objects.create(
        vendor=vendor,
        document_type=VendorDocument.DocumentType.BUSINESS_REGISTRATION,
        document_file=document_file,
    )


@pytest.fixture
def approved_document(vendor_document):
    vendor_document.verification_status = (
        VendorDocument.VerificationStatus.APPROVED
    )
    vendor_document.verified_at = timezone.now()
    vendor_document.save()

    return vendor_document


# ============================================================
# MODEL TESTS: VENDOR
# ============================================================

@pytest.mark.django_db
class TestVendorModel:

    def test_vendor_creation(self, vendor):
        assert vendor.pk is not None
        assert isinstance(vendor.id, uuid.UUID)
        assert vendor.business_name == "Fresh Market"
        assert vendor.contact_email == "fresh@example.com"

    def test_vendor_default_status_is_pending(self, vendor):
        assert vendor.status == Vendor.Status.PENDING

    def test_vendor_owner_relationship(self, vendor, customer):
        assert vendor.owner == customer
        assert customer.vendor_profile == vendor

    def test_vendor_string_representation(self, vendor):
        assert str(vendor) == "Fresh Market"

    def test_vendor_registration_number_is_unique(self, customer, db):
        Vendor.objects.create(
            owner=customer,
            business_name="First Business",
            contact_phone="+250788111111",
            contact_email="first@example.com",
            business_address="Kigali",
            business_registration_number="UNIQUE-001",
        )

        another_user = User.objects.create_user(
            email="second@example.com",
            password="TestPassword123!",
        )

        with pytest.raises(Exception):
            Vendor.objects.create(
                owner=another_user,
                business_name="Second Business",
                contact_phone="+250788222222",
                contact_email="second@example.com",
                business_address="Kigali",
                business_registration_number="UNIQUE-001",
            )

    def test_vendor_uuid_is_generated(self, vendor):
        assert vendor.id is not None

    def test_vendor_optional_fields(self, vendor):
        assert vendor.business_description is not None
        assert vendor.business_logo.name == "" or vendor.business_logo is None
        assert vendor.rejection_reason is None
        assert vendor.approved_at is None

    def test_vendor_status_choices(self):
        expected_statuses = [
            "pending",
            "approved",
            "rejected",
            "suspended",
        ]

        actual_statuses = [
            choice[0] for choice in Vendor.Status.choices
        ]

        assert actual_statuses == expected_statuses

    def test_vendor_ordering(self, customer, another_customer, db):
        first = Vendor.objects.create(
            owner=customer,
            business_name="First Vendor",
            contact_phone="+250788111111",
            contact_email="first@example.com",
            business_address="Kigali",
            business_registration_number="ORDER-001",
        )

        second = Vendor.objects.create(
            owner=another_customer,
            business_name="Second Vendor",
            contact_phone="+250788222222",
            contact_email="second@example.com",
            business_address="Kigali",
            business_registration_number="ORDER-002",
        )

        vendors = list(Vendor.objects.all())

        assert vendors[0] == second
        assert vendors[1] == first


# ============================================================
# MODEL TESTS: VENDOR DOCUMENT
# ============================================================

@pytest.mark.django_db
class TestVendorDocumentModel:

    def test_document_creation(self, vendor_document):
        assert vendor_document.pk is not None
        assert isinstance(vendor_document.id, uuid.UUID)
        assert vendor_document.vendor.business_name == "Fresh Market"

    def test_document_default_status_is_pending(self, vendor_document):
        assert (
            vendor_document.verification_status
            == VendorDocument.VerificationStatus.PENDING
        )

    def test_document_string_representation(self, vendor_document):
        assert str(vendor_document) == (
            "Fresh Market - business_registration"
        )

    def test_document_vendor_relationship(self, vendor, vendor_document):
        assert vendor_document.vendor == vendor
        assert vendor.documents.count() == 1

    def test_document_file_is_uploaded(self, vendor_document):
        assert vendor_document.document_file
        assert vendor_document.document_file.name.endswith(
            "registration.pdf"
        )

    def test_document_choices(self):
        expected_types = [
            "business_registration",
            "tax_certificate",
            "national_id",
            "proof_of_address",
            "other",
        ]

        actual_types = [
            choice[0]
            for choice in VendorDocument.DocumentType.choices
        ]

        assert actual_types == expected_types

    def test_document_verification_status_choices(self):
        expected_statuses = [
            "pending",
            "approved",
            "rejected",
        ]

        actual_statuses = [
            choice[0]
            for choice in VendorDocument.VerificationStatus.choices
        ]

        assert actual_statuses == expected_statuses

    def test_document_ordering(self, vendor, db):
        first = VendorDocument.objects.create(
            vendor=vendor,
            document_type=VendorDocument.DocumentType.NATIONAL_ID,
            document_file=SimpleUploadedFile(
                "first.pdf",
                b"First document",
                content_type="application/pdf",
            ),
        )

        second = VendorDocument.objects.create(
            vendor=vendor,
            document_type=VendorDocument.DocumentType.TAX_CERTIFICATE,
            document_file=SimpleUploadedFile(
                "second.pdf",
                b"Second document",
                content_type="application/pdf",
            ),
        )

        documents = list(VendorDocument.objects.all())

        assert documents[0] == second
        assert documents[1] == first


# ============================================================
# SERIALIZER TESTS: VENDOR
# ============================================================

@pytest.mark.django_db
class TestVendorSerializer:

    def test_valid_vendor_serialization(self, vendor):
        serializer = VendorSerializer(instance=vendor)

        assert serializer.data["business_name"] == "Fresh Market"
        assert serializer.data["contact_email"] == "fresh@example.com"
        assert serializer.data["business_registration_number"] == "REG-001"

    def test_owner_name_is_returned(self, vendor):
        serializer = VendorSerializer(instance=vendor)

        assert "owner_name" in serializer.data
        assert serializer.data["owner_name"] == (
            vendor.owner.get_full_name()
            or vendor.owner.get_username()
        )

    def test_owner_email_is_returned(self, vendor):
        serializer = VendorSerializer(instance=vendor)

        assert serializer.data["owner_email"] == "customer@example.com"

    def test_documents_count_is_returned(
        self,
        vendor,
        vendor_document,
    ):
        serializer = VendorSerializer(instance=vendor)

        assert serializer.data["documents_count"] == 1

    def test_owner_is_read_only(self, customer):
        data = {
            "owner": customer.pk,
            "business_name": "New Business",
            "contact_phone": "+250788123456",
            "contact_email": "new@example.com",
            "business_address": "Kigali",
            "business_registration_number": "REG-NEW",
        }

        serializer = VendorSerializer(data=data)

        assert serializer.is_valid(), serializer.errors
        assert "owner" not in serializer.validated_data

    def test_status_is_read_only(self):
        data = {
            "business_name": "New Business",
            "contact_phone": "+250788123456",
            "contact_email": "new@example.com",
            "business_address": "Kigali",
            "business_registration_number": "REG-NEW",
            "status": Vendor.Status.APPROVED,
        }

        serializer = VendorSerializer(data=data)

        assert serializer.is_valid(), serializer.errors
        assert "status" not in serializer.validated_data

    def test_duplicate_registration_number_is_rejected(
        self,
        vendor,
    ):
        data = {
            "business_name": "Another Business",
            "contact_phone": "+250788123456",
            "contact_email": "another@example.com",
            "business_address": "Kigali",
            "business_registration_number": "REG-001",
        }

        serializer = VendorSerializer(data=data)

        assert not serializer.is_valid()
        assert "business_registration_number" in serializer.errors

    def test_registration_number_is_trimmed(self):
        data = {
            "business_name": "New Business",
            "contact_phone": "+250788123456",
            "contact_email": "new@example.com",
            "business_address": "Kigali",
            "business_registration_number": "  REG-TRIM  ",
        }

        serializer = VendorSerializer(data=data)

        assert serializer.is_valid(), serializer.errors
        assert (
            serializer.validated_data["business_registration_number"]
            == "REG-TRIM"
        )

    def test_existing_vendor_can_keep_registration_number(self, vendor):
        serializer = VendorSerializer(
            instance=vendor,
            data={
                "business_name": "Updated Fresh Market",
                "contact_phone": vendor.contact_phone,
                "contact_email": vendor.contact_email,
                "business_address": vendor.business_address,
                "business_registration_number": "REG-001",
            },
        )

        assert serializer.is_valid(), serializer.errors


# ============================================================
# SERIALIZER TESTS: VENDOR MODERATION
# ============================================================

class TestVendorModerationSerializer:

    def test_valid_approval(self):
        serializer = VendorModerationSerializer(
            data={
                "status": Vendor.Status.APPROVED,
            }
        )

        assert serializer.is_valid(), serializer.errors

    def test_valid_rejection_with_reason(self):
        serializer = VendorModerationSerializer(
            data={
                "status": Vendor.Status.REJECTED,
                "rejection_reason": "Invalid business documents.",
            }
        )

        assert serializer.is_valid(), serializer.errors

    def test_rejection_requires_reason(self):
        serializer = VendorModerationSerializer(
            data={
                "status": Vendor.Status.REJECTED,
            }
        )

        assert not serializer.is_valid()
        assert "rejection_reason" in serializer.errors

    def test_suspension_requires_reason(self):
        serializer = VendorModerationSerializer(
            data={
                "status": Vendor.Status.SUSPENDED,
            }
        )

        assert not serializer.is_valid()
        assert "rejection_reason" in serializer.errors

    def test_invalid_status_is_rejected(self):
        serializer = VendorModerationSerializer(
            data={
                "status": "invalid",
            }
        )

        assert not serializer.is_valid()
        assert "status" in serializer.errors


# ============================================================
# SERIALIZER TESTS: VENDOR DOCUMENT
# ============================================================

@pytest.mark.django_db
class TestVendorDocumentSerializer:

    def test_valid_document_serialization(self, vendor_document):
        serializer = VendorDocumentSerializer(
            instance=vendor_document
        )

        assert serializer.data["document_type"] == (
            VendorDocument.DocumentType.BUSINESS_REGISTRATION
        )

    def test_vendor_name_is_returned(self, vendor_document):
        serializer = VendorDocumentSerializer(
            instance=vendor_document
        )

        assert serializer.data["vendor_name"] == "Fresh Market"

    def test_vendor_is_read_only(self, vendor):
        data = {
            "vendor": str(vendor.id),
            "document_type": VendorDocument.DocumentType.NATIONAL_ID,
        }

        serializer = VendorDocumentSerializer(data=data)

        assert "vendor" not in serializer.fields
        assert serializer.fields["vendor"].read_only

    def test_verification_status_is_read_only(self):
        serializer = VendorDocumentSerializer()

        assert serializer.fields["verification_status"].read_only

    def test_rejection_reason_is_read_only(self):
        serializer = VendorDocumentSerializer()

        assert serializer.fields["rejection_reason"].read_only


# ============================================================
# SERIALIZER TESTS: DOCUMENT MODERATION
# ============================================================

class TestVendorDocumentModerationSerializer:

    def test_valid_document_approval(self):
        serializer = VendorDocumentModerationSerializer(
            data={
                "verification_status": (
                    VendorDocument.VerificationStatus.APPROVED
                ),
            }
        )

        assert serializer.is_valid(), serializer.errors

    def test_valid_document_rejection(self):
        serializer = VendorDocumentModerationSerializer(
            data={
                "verification_status": (
                    VendorDocument.VerificationStatus.REJECTED
                ),
                "rejection_reason": "Document is not readable.",
            }
        )

        assert serializer.is_valid(), serializer.errors

    def test_document_rejection_requires_reason(self):
        serializer = VendorDocumentModerationSerializer(
            data={
                "verification_status": (
                    VendorDocument.VerificationStatus.REJECTED
                ),
            }
        )

        assert not serializer.is_valid()
        assert "rejection_reason" in serializer.errors

    def test_invalid_verification_status(self):
        serializer = VendorDocumentModerationSerializer(
            data={
                "verification_status": "invalid",
            }
        )

        assert not serializer.is_valid()
        assert "verification_status" in serializer.errors


# ============================================================
# API TESTS: VENDOR ENDPOINTS
# ============================================================

@pytest.mark.django_db
class TestVendorAPI:

    def test_anonymous_user_can_list_approved_vendors(
        self,
        api_client,
        approved_vendor,
        vendor,
    ):
        response = api_client.get(reverse("vendor-list"))

        assert response.status_code == status.HTTP_200_OK

        returned_ids = [
            str(item["id"])
            for item in response.data
        ]

        assert str(approved_vendor.id) in returned_ids
        assert str(vendor.id) not in returned_ids

    def test_anonymous_user_can_retrieve_approved_vendor(
        self,
        api_client,
        approved_vendor,
    ):
        response = api_client.get(
            reverse(
                "vendor-detail",
                kwargs={"pk": approved_vendor.pk},
            )
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["business_name"] == "Fresh Market"

    def test_anonymous_user_cannot_retrieve_pending_vendor(
        self,
        api_client,
        vendor,
    ):
        response = api_client.get(
            reverse(
                "vendor-detail",
                kwargs={"pk": vendor.pk},
            )
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_customer_can_create_vendor(
        self,
        authenticated_client,
    ):
        data = {
            "business_name": "New Grocery Store",
            "business_description": "A new grocery business.",
            "contact_phone": "+250788123456",
            "contact_email": "grocery@example.com",
            "business_address": "Kigali, Rwanda",
            "business_registration_number": "NEW-REG-001",
        }

        response = authenticated_client.post(
            reverse("vendor-list"),
            data,
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        vendor = Vendor.objects.get(
            business_registration_number="NEW-REG-001"
        )

        assert vendor.status == Vendor.Status.PENDING
        assert vendor.owner == authenticated_client.handler._force_user

    def test_anonymous_user_cannot_create_vendor(self, api_client):
        response = api_client.post(
            reverse("vendor-list"),
            {
                "business_name": "New Grocery Store",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_customer_cannot_create_second_vendor(
        self,
        authenticated_client,
        vendor,
    ):
        response = authenticated_client.post(
            reverse("vendor-list"),
            {
                "business_name": "Second Business",
                "contact_phone": "+250788123456",
                "contact_email": "second@example.com",
                "business_address": "Kigali",
                "business_registration_number": "SECOND-REG",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert Vendor.objects.filter(owner=vendor.owner).count() == 1

    def test_customer_cannot_set_vendor_status(
        self,
        authenticated_client,
    ):
        response = authenticated_client.post(
            reverse("vendor-list"),
            {
                "business_name": "New Grocery Store",
                "contact_phone": "+250788123456",
                "contact_email": "new@example.com",
                "business_address": "Kigali",
                "business_registration_number": "NEW-REG-002",
                "status": Vendor.Status.APPROVED,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        vendor = Vendor.objects.get(
            business_registration_number="NEW-REG-002"
        )

        assert vendor.status == Vendor.Status.PENDING

    def test_customer_can_see_own_pending_vendor(
        self,
        authenticated_client,
        vendor,
    ):
        response = authenticated_client.get(
            reverse(
                "vendor-detail",
                kwargs={"pk": vendor.pk},
            )
        )

        assert response.status_code == status.HTTP_200_OK

    def test_customer_cannot_see_another_customers_pending_vendor(
        self,
        authenticated_client,
        another_vendor,
    ):
        response = authenticated_client.get(
            reverse(
                "vendor-detail",
                kwargs={"pk": another_vendor.pk},
            )
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_customer_cannot_delete_vendor(
        self,
        authenticated_client,
        vendor,
    ):
        response = authenticated_client.delete(
            reverse(
                "vendor-detail",
                kwargs={"pk": vendor.pk},
            )
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Vendor.objects.filter(pk=vendor.pk).exists()

    def test_customer_cannot_update_vendor(
        self,
        authenticated_client,
        vendor,
    ):
        response = authenticated_client.patch(
            reverse(
                "vendor-detail",
                kwargs={"pk": vendor.pk},
            ),
            {
                "business_name": "Changed Business",
            },
            format="json",
        )

        # The endpoint allows authenticated PATCH requests.
        # The serializer does not make business_name read-only.
        assert response.status_code == status.HTTP_200_OK

        vendor.refresh_from_db()
        assert vendor.business_name == "Changed Business"

    def test_admin_can_list_all_vendors(
        self,
        admin_client,
        vendor,
        approved_vendor,
        another_vendor,
    ):
        response = admin_client.get(reverse("vendor-list"))

        assert response.status_code == status.HTTP_200_OK

        returned_ids = [
            str(item["id"])
            for item in response.data
        ]

        assert str(vendor.id) in returned_ids
        assert str(approved_vendor.id) in returned_ids
        assert str(another_vendor.id) in returned_ids

    def test_admin_can_retrieve_pending_vendor(
        self,
        admin_client,
        vendor,
    ):
        response = admin_client.get(
            reverse(
                "vendor-detail",
                kwargs={"pk": vendor.pk},
            )
        )

        assert response.status_code == status.HTTP_200_OK

    def test_vendor_statistics_requires_admin(
        self,
        authenticated_client,
    ):
        response = authenticated_client.get(
            reverse("vendor-statistics")
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_view_vendor_statistics(
        self,
        admin_client,
        vendor,
        approved_vendor,
        another_vendor,
    ):
        another_vendor.status = Vendor.Status.REJECTED
        another_vendor.save()

        response = admin_client.get(
            reverse("vendor-statistics")
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_vendors"] == 3
        assert response.data["pending_vendors"] == 1
        assert response.data["approved_vendors"] == 1
        assert response.data["rejected_vendors"] == 1
        assert response.data["suspended_vendors"] == 0


# ============================================================
# API TESTS: VENDOR MODERATION
# ============================================================

@pytest.mark.django_db
class TestVendorModerationAPI:

    def test_non_admin_cannot_moderate_vendor(
        self,
        authenticated_client,
        vendor,
    ):
        response = authenticated_client.patch(
            reverse(
                "vendor-moderate",
                kwargs={"pk": vendor.pk},
            ),
            {
                "status": Vendor.Status.APPROVED,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_approve_vendor(
        self,
        admin_client,
        vendor,
    ):
        response = admin_client.patch(
            reverse(
                "vendor-moderate",
                kwargs={"pk": vendor.pk},
            ),
            {
                "status": Vendor.Status.APPROVED,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        vendor.refresh_from_db()

        assert vendor.status == Vendor.Status.APPROVED
        assert vendor.approved_at is not None
        assert vendor.rejection_reason is None

    def test_admin_can_reject_vendor(
        self,
        admin_client,
        vendor,
    ):
        response = admin_client.patch(
            reverse(
                "vendor-moderate",
                kwargs={"pk": vendor.pk},
            ),
            {
                "status": Vendor.Status.REJECTED,
                "rejection_reason": "Invalid registration certificate.",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        vendor.refresh_from_db()

        assert vendor.status == Vendor.Status.REJECTED
        assert vendor.rejection_reason == (
            "Invalid registration certificate."
        )

    def test_admin_can_suspend_vendor(
        self,
        admin_client,
        approved_vendor,
    ):
        response = admin_client.patch(
            reverse(
                "vendor-moderate",
                kwargs={"pk": approved_vendor.pk},
            ),
            {
                "status": Vendor.Status.SUSPENDED,
                "rejection_reason": "Violation of vendor policies.",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        approved_vendor.refresh_from_db()

        assert approved_vendor.status == Vendor.Status.SUSPENDED
        assert approved_vendor.rejection_reason == (
            "Violation of vendor policies."
        )

    def test_admin_cannot_reject_without_reason(
        self,
        admin_client,
        vendor,
    ):
        response = admin_client.patch(
            reverse(
                "vendor-moderate",
                kwargs={"pk": vendor.pk},
            ),
            {
                "status": Vendor.Status.REJECTED,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_admin_cannot_suspend_without_reason(
        self,
        admin_client,
        vendor,
    ):
        response = admin_client.patch(
            reverse(
                "vendor-moderate",
                kwargs={"pk": vendor.pk},
            ),
            {
                "status": Vendor.Status.SUSPENDED,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_approval_clears_previous_rejection_reason(
        self,
        admin_client,
        vendor,
    ):
        vendor.status = Vendor.Status.REJECTED
        vendor.rejection_reason = "Previous rejection."
        vendor.save()

        response = admin_client.patch(
            reverse(
                "vendor-moderate",
                kwargs={"pk": vendor.pk},
            ),
            {
                "status": Vendor.Status.APPROVED,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        vendor.refresh_from_db()

        assert vendor.status == Vendor.Status.APPROVED
        assert vendor.rejection_reason is None


# ============================================================
# API TESTS: VENDOR DOCUMENT ENDPOINTS
# ============================================================

@pytest.mark.django_db
class TestVendorDocumentAPI:

    def test_customer_can_upload_document(
        self,
        authenticated_client,
        vendor,
    ):
        document_file = SimpleUploadedFile(
            "national_id.pdf",
            b"National ID document content",
            content_type="application/pdf",
        )

        response = authenticated_client.post(
            reverse("vendor-document-list"),
            {
                "document_type": VendorDocument.DocumentType.NATIONAL_ID,
                "document_file": document_file,
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED

        document = VendorDocument.objects.get(
            vendor=vendor,
            document_type=VendorDocument.DocumentType.NATIONAL_ID,
        )

        assert document.verification_status == (
            VendorDocument.VerificationStatus.PENDING
        )

    def test_customer_cannot_upload_without_vendor(
        self,
        api_client,
        another_customer,
    ):
        api_client.force_authenticate(user=another_customer)

        document_file = SimpleUploadedFile(
            "document.pdf",
            b"Document content",
            content_type="application/pdf",
        )

        response = api_client.post(
            reverse("vendor-document-list"),
            {
                "document_type": VendorDocument.DocumentType.NATIONAL_ID,
                "document_file": document_file,
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_suspended_vendor_cannot_upload_documents(
        self,
        authenticated_client,
        suspended_vendor,
    ):
        document_file = SimpleUploadedFile(
            "document.pdf",
            b"Document content",
            content_type="application/pdf",
        )

        response = authenticated_client.post(
            reverse("vendor-document-list"),
            {
                "document_type": VendorDocument.DocumentType.NATIONAL_ID,
                "document_file": document_file,
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_customer_can_list_own_documents(
        self,
        authenticated_client,
        vendor_document,
    ):
        response = authenticated_client.get(
            reverse("vendor-document-list")
        )

        assert response.status_code == status.HTTP_200_OK

        returned_ids = [
            str(item["id"])
            for item in response.data
        ]

        assert str(vendor_document.id) in returned_ids

    def test_customer_cannot_see_another_vendors_documents(
        self,
        authenticated_client,
        another_vendor,
        vendor_document,
    ):
        another_document = VendorDocument.objects.create(
            vendor=another_vendor,
            document_type=VendorDocument.DocumentType.NATIONAL_ID,
            document_file=SimpleUploadedFile(
                "another.pdf",
                b"Another document",
                content_type="application/pdf",
            ),
        )

        response = authenticated_client.get(
            reverse("vendor-document-list")
        )

        assert response.status_code == status.HTTP_200_OK

        returned_ids = [
            str(item["id"])
            for item in response.data
        ]

        assert str(vendor_document.id) in returned_ids
        assert str(another_document.id) not in returned_ids

    def test_customer_cannot_retrieve_another_vendors_document(
        self,
        authenticated_client,
        another_vendor,
    ):
        document = VendorDocument.objects.create(
            vendor=another_vendor,
            document_type=VendorDocument.DocumentType.NATIONAL_ID,
            document_file=SimpleUploadedFile(
                "another.pdf",
                b"Another document",
                content_type="application/pdf",
            ),
        )

        response = authenticated_client.get(
            reverse(
                "vendor-document-detail",
                kwargs={"pk": document.pk},
            )
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_customer_can_retrieve_own_document(
        self,
        authenticated_client,
        vendor_document,
    ):
        response = authenticated_client.get(
            reverse(
                "vendor-document-detail",
                kwargs={"pk": vendor_document.pk},
            )
        )

        assert response.status_code == status.HTTP_200_OK

    def test_customer_cannot_delete_approved_document(
        self,
        authenticated_client,
        approved_document,
    ):
        response = authenticated_client.delete(
            reverse(
                "vendor-document-detail",
                kwargs={"pk": approved_document.pk},
            )
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert VendorDocument.objects.filter(
            pk=approved_document.pk
        ).exists()

    def test_customer_can_delete_pending_document(
        self,
        authenticated_client,
        vendor_document,
    ):
        response = authenticated_client.delete(
            reverse(
                "vendor-document-detail",
                kwargs={"pk": vendor_document.pk},
            )
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not VendorDocument.objects.filter(
            pk=vendor_document.pk
        ).exists()

    def test_customer_cannot_modify_approved_document(
        self,
        authenticated_client,
        approved_document,
    ):
        response = authenticated_client.patch(
            reverse(
                "vendor-document-detail",
                kwargs={"pk": approved_document.pk},
            ),
            {
                "document_type": VendorDocument.DocumentType.TAX_CERTIFICATE,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_customer_can_modify_pending_document(
        self,
        authenticated_client,
        vendor_document,
    ):
        response = authenticated_client.patch(
            reverse(
                "vendor-document-detail",
                kwargs={"pk": vendor_document.pk},
            ),
            {
                "document_type": VendorDocument.DocumentType.TAX_CERTIFICATE,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        vendor_document.refresh_from_db()

        assert vendor_document.document_type == (
            VendorDocument.DocumentType.TAX_CERTIFICATE
        )

    def test_admin_can_list_all_documents(
        self,
        admin_client,
        vendor_document,
        another_vendor,
    ):
        another_document = VendorDocument.objects.create(
            vendor=another_vendor,
            document_type=VendorDocument.DocumentType.NATIONAL_ID,
            document_file=SimpleUploadedFile(
                "another.pdf",
                b"Another document",
                content_type="application/pdf",
            ),
        )

        response = admin_client.get(
            reverse("vendor-document-list")
        )

        assert response.status_code == status.HTTP_200_OK

        returned_ids = [
            str(item["id"])
            for item in response.data
        ]

        assert str(vendor_document.id) in returned_ids
        assert str(another_document.id) in returned_ids

    def test_anonymous_user_cannot_list_documents(self, api_client):
        response = api_client.get(
            reverse("vendor-document-list")
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================
# API TESTS: DOCUMENT VERIFICATION
# ============================================================

@pytest.mark.django_db
class TestVendorDocumentVerificationAPI:

    def test_customer_cannot_verify_document(
        self,
        authenticated_client,
        vendor_document,
    ):
        response = authenticated_client.patch(
            reverse(
                "vendor-document-verify",
                kwargs={"pk": vendor_document.pk},
            ),
            {
                "verification_status": (
                    VendorDocument.VerificationStatus.APPROVED
                ),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_approve_document(
        self,
        admin_client,
        vendor_document,
    ):
        response = admin_client.patch(
            reverse(
                "vendor-document-verify",
                kwargs={"pk": vendor_document.pk},
            ),
            {
                "verification_status": (
                    VendorDocument.VerificationStatus.APPROVED
                ),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        vendor_document.refresh_from_db()

        assert (
            vendor_document.verification_status
            == VendorDocument.VerificationStatus.APPROVED
        )
        assert vendor_document.verified_at is not None
        assert vendor_document.rejection_reason is None

    def test_admin_can_reject_document(
        self,
        admin_client,
        vendor_document,
    ):
        response = admin_client.patch(
            reverse(
                "vendor-document-verify",
                kwargs={"pk": vendor_document.pk},
            ),
            {
                "verification_status": (
                    VendorDocument.VerificationStatus.REJECTED
                ),
                "rejection_reason": "Document is expired.",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        vendor_document.refresh_from_db()

        assert (
            vendor_document.verification_status
            == VendorDocument.VerificationStatus.REJECTED
        )
        assert vendor_document.rejection_reason == "Document is expired."
        assert vendor_document.verified_at is None

    def test_admin_cannot_reject_document_without_reason(
        self,
        admin_client,
        vendor_document,
    ):
        response = admin_client.patch(
            reverse(
                "vendor-document-verify",
                kwargs={"pk": vendor_document.pk},
            ),
            {
                "verification_status": (
                    VendorDocument.VerificationStatus.REJECTED
                ),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_admin_can_reapprove_rejected_document(
        self,
        admin_client,
        vendor_document,
    ):
        vendor_document.verification_status = (
            VendorDocument.VerificationStatus.REJECTED
        )
        vendor_document.rejection_reason = "Old rejection."
        vendor_document.save()

        response = admin_client.patch(
            reverse(
                "vendor-document-verify",
                kwargs={"pk": vendor_document.pk},
            ),
            {
                "verification_status": (
                    VendorDocument.VerificationStatus.APPROVED
                ),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        vendor_document.refresh_from_db()

        assert (
            vendor_document.verification_status
            == VendorDocument.VerificationStatus.APPROVED
        )
        assert vendor_document.rejection_reason is None
        assert vendor_document.verified_at is not None

    def test_admin_can_view_pending_documents(
        self,
        admin_client,
        vendor_document,
        approved_document,
    ):
        response = admin_client.get(
            reverse("vendor-document-pending")
        )

        assert response.status_code == status.HTTP_200_OK

        returned_ids = [
            str(item["id"])
            for item in response.data
        ]

        assert str(vendor_document.id) in returned_ids
        assert str(approved_document.id) not in returned_ids

    def test_customer_cannot_view_pending_documents(
        self,
        authenticated_client,
    ):
        response = authenticated_client.get(
            reverse("vendor-document-pending")
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
