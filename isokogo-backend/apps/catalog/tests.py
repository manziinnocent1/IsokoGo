"""
Pytest tests for the catalog app (models, serializers, viewsets).

Requirements:
    pip install pytest pytest-django Pillow

BEFORE RUNNING, edit the `make_vendor` fixture: Product.vendor points at
"vendors.Vendor" and I don't know that model's required fields.

The viewsets are called directly with APIRequestFactory, so these tests do not
depend on your urls.py. "Staff" users are created with role="admin" because the
accounts User model derives `is_staff` from its role.
"""
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIRequestFactory, force_authenticate

from .models import (
    Brand,
    Category,
    Product,
    ProductAttribute,
    ProductAttributeValue,
    ProductImage,
    ProductVariant,
)
from .serializers import (
    BrandSerializer,
    CategorySerializer,
    ProductAttributeSerializer,
    ProductAttributeValueSerializer,
    ProductImageSerializer,
    ProductSerializer,
    ProductVariantSerializer,
)
from .views import (
    BrandViewSet,
    CategoryViewSet,
    ProductAttributeValueViewSet,
    ProductAttributeViewSet,
    ProductImageViewSet,
    ProductVariantViewSet,
    ProductViewSet,
)

pytestmark = pytest.mark.django_db

PASSWORD = "Tr0ub4dor&Zebra-Lamp-92"

ALL_VIEWSETS = [
    CategoryViewSet,
    BrandViewSet,
    ProductViewSet,
    ProductVariantViewSet,
    ProductImageViewSet,
    ProductAttributeViewSet,
    ProductAttributeValueViewSet,
]


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def make_user():
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        n = counter["n"]
        params = {
            "email": f"person{n}@example.com",
            "password": PASSWORD,
            "phone_number": f"0788{n:06d}",
            "first_name": "Test",
            "last_name": f"Person{n}",
        }
        params.update(overrides)
        return get_user_model().objects.create_user(**params)

    return _make


@pytest.fixture
def staff(make_user):
    return make_user(role="admin")


@pytest.fixture
def customer(make_user):
    return make_user()


@pytest.fixture
def make_vendor():
    """EDIT ME: return a saved vendors.Vendor (fill in its required fields)."""
    counter = {"n": 0}
    Vendor = apps.get_model("vendors", "Vendor")

    def _make(**overrides):
        counter["n"] += 1
        fields = {
            # "name": f"Vendor {counter['n']}",
        }
        fields.update(overrides)
        return Vendor.objects.create(**fields)

    return _make


@pytest.fixture
def vendor(make_vendor):
    return make_vendor()


@pytest.fixture
def make_category():
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        n = counter["n"]
        fields = {"name": f"Category {n}", "slug": f"category-{n}"}
        fields.update(overrides)
        return Category.objects.create(**fields)

    return _make


@pytest.fixture
def category(make_category):
    return make_category()


@pytest.fixture
def make_brand():
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        fields = {"name": f"Brand {counter['n']}"}
        fields.update(overrides)
        return Brand.objects.create(**fields)

    return _make


@pytest.fixture
def make_product(vendor, category):
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        n = counter["n"]
        fields = {
            "name": f"Product {n}",
            "slug": f"product-{n}",
            "sku": f"SKU-{n}",
            "category": category,
            "vendor": vendor,
            "base_price": Decimal("10.00"),
        }
        fields.update(overrides)
        return Product.objects.create(**fields)

    return _make


@pytest.fixture
def product(make_product):
    return make_product()


@pytest.fixture
def make_variant(product):
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        n = counter["n"]
        fields = {
            "product": product,
            "name": f"Variant {n}",
            "sku": f"VAR-{n}",
            "size_value": Decimal("500"),
            "size_unit": "g",
            "selling_price": Decimal("4.50"),
        }
        fields.update(overrides)
        return ProductVariant.objects.create(**fields)

    return _make


@pytest.fixture
def make_attribute():
    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        fields = {"name": f"Attribute {counter['n']}"}
        fields.update(overrides)
        return ProductAttribute.objects.create(**fields)

    return _make


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def png_upload(name="photo.png"):
    buf = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@pytest.fixture
def factory():
    return APIRequestFactory()


ACTIONS = {
    "list": ("get", {"get": "list"}),
    "create": ("post", {"post": "create"}),
    "retrieve": ("get", {"get": "retrieve"}),
    "update": ("put", {"put": "update"}),
    "partial_update": ("patch", {"patch": "partial_update"}),
    "destroy": ("delete", {"delete": "destroy"}),
}


@pytest.fixture
def call(factory):
    """call(ProductViewSet, "list", user=u, query={...}, pk=..., data={...}, fmt="json")"""

    def _call(viewset, action, user=None, pk=None, data=None, query=None, fmt="json"):
        http_method, mapping = ACTIONS[action]
        make = getattr(factory, http_method)
        if http_method == "get":
            request = make("/test/", query or {})
        elif http_method == "delete":
            request = make("/test/")
        else:
            request = make("/test/", data or {}, format=fmt)
        if user is not None:
            force_authenticate(request, user=user)
        kwargs = {"pk": str(pk)} if pk is not None else {}
        return viewset.as_view(mapping)(request, **kwargs)

    return _call


def rows(resp):
    """List rows whether or not you've configured pagination."""
    if isinstance(resp.data, dict) and "results" in resp.data:
        return resp.data["results"]
    return resp.data


def ids(resp):
    return [str(r["id"]) for r in rows(resp)]


def backdate(model, obj, field, minutes):
    model.objects.filter(pk=obj.pk).update(**{field: timezone.now() - timedelta(minutes=minutes)})


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class TestCategoryModel:
    def test_defaults_and_str(self, category):
        assert category.is_active is True
        assert category.display_order == 0
        assert str(category) == category.name

    def test_ordering_by_display_order_then_name(self, make_category):
        c = make_category(name="C", display_order=1)
        b = make_category(name="B", display_order=0)
        a = make_category(name="A", display_order=0)
        assert list(Category.objects.all()) == [a, b, c]

    def test_slug_unique(self, category):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Category.objects.create(name="Dup", slug=category.slug)

    def test_deleting_parent_cascades_to_children(self, make_category):
        parent = make_category()
        child = make_category(parent=parent)
        parent.delete()
        assert not Category.objects.filter(pk=child.pk).exists()


class TestBrandModel:
    def test_str_and_defaults(self, make_brand):
        brand = make_brand(name="Acme")
        assert str(brand) == "Acme"
        assert brand.is_active is True


class TestProductModel:
    def test_uuid_pk_and_str(self, product):
        assert str(product) == product.name
        assert len(str(product.pk)) == 36

    def test_defaults(self, product):
        assert product.is_available is True
        assert product.is_featured is False
        assert product.is_perishable is False
        assert product.requires_refrigeration is False
        assert product.brand is None

    def test_sku_slug_unique(self, product, make_product):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_product(sku=product.sku)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_product(slug=product.slug)

    def test_barcode_unique_but_many_nulls_allowed(self, make_product):
        make_product(barcode=None)
        make_product(barcode=None)
        make_product(barcode="123")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_product(barcode="123")

    def test_category_is_protected(self, product, category):
        with pytest.raises(ProtectedError):
            category.delete()

    def test_deleting_brand_sets_null(self, make_product, make_brand):
        brand = make_brand()
        p = make_product(brand=brand)
        brand.delete()
        p.refresh_from_db()
        assert p.brand is None


class TestProductVariantModel:
    def test_str(self, product, make_variant):
        v = make_variant(name="1kg")
        assert str(v) == f"{product.name} - 1kg"

    def test_sku_unique(self, make_variant):
        v = make_variant()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_variant(sku=v.sku)

    def test_cascade_delete_with_product(self, product, make_variant):
        make_variant()
        product.delete()
        assert ProductVariant.objects.count() == 0


class TestProductImageModel:
    def make(self, product, **kw):
        return ProductImage.objects.create(product=product, image="product_images/a.jpg", **kw)

    def test_only_one_primary_per_product(self, product):
        self.make(product, is_primary=True)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                self.make(product, is_primary=True)

    def test_many_non_primary_allowed(self, product):
        self.make(product)
        self.make(product)
        assert product.images.count() == 2

    def test_each_product_can_have_its_own_primary(self, product, make_product):
        self.make(product, is_primary=True)
        self.make(make_product(), is_primary=True)
        assert ProductImage.objects.filter(is_primary=True).count() == 2

    def test_ordering(self, product):
        b = self.make(product, display_order=2)
        a = self.make(product, display_order=1)
        assert list(product.images.all()) == [a, b]


class TestProductAttributeModels:
    def test_attribute_name_unique(self, make_attribute):
        attr = make_attribute()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ProductAttribute.objects.create(name=attr.name)

    def test_one_value_per_attribute_per_product(self, product, make_attribute):
        attr = make_attribute()
        ProductAttributeValue.objects.create(product=product, attribute=attr, value="Red")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ProductAttributeValue.objects.create(product=product, attribute=attr, value="Blue")

    def test_str(self, product, make_attribute):
        attr = make_attribute(name="Color")
        val = ProductAttributeValue.objects.create(product=product, attribute=attr, value="Red")
        assert str(attr) == "Color"
        assert str(val) == "Color: Red"


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
class TestCategorySerializer:
    def test_fields_include_subcategories(self, category):
        assert "subcategories" in CategorySerializer(category).data

    def test_nested_subcategories_only_active(self, make_category):
        parent = make_category()
        active = make_category(parent=parent)
        make_category(parent=parent, is_active=False)
        data = CategorySerializer(parent).data
        assert [c["id"] for c in data["subcategories"]] == [active.pk]

    def test_nesting_is_recursive(self, make_category):
        root = make_category()
        child = make_category(parent=root)
        grandchild = make_category(parent=child)
        data = CategorySerializer(root).data
        assert data["subcategories"][0]["subcategories"][0]["id"] == grandchild.pk

    def test_read_only_fields_ignored(self):
        s = CategorySerializer(data={"name": "X", "slug": "x", "id": 999})
        assert s.is_valid(), s.errors
        assert "id" not in s.validated_data


class TestBrandSerializer:
    def test_roundtrip(self, make_brand):
        brand = make_brand()
        data = BrandSerializer(brand).data
        assert set(data) == {"id", "name", "description", "logo", "is_active", "created_at", "updated_at"}

    def test_name_required(self):
        assert not BrandSerializer(data={}).is_valid()


class TestProductSerializer:
    def payload(self, category, vendor, **overrides):
        data = {
            "name": "Mango",
            "slug": "mango",
            "sku": "MANGO-1",
            "category": category.pk,
            "vendor": vendor.pk,
            "base_price": "3.50",
        }
        data.update(overrides)
        return data

    def test_valid(self, category, vendor):
        s = ProductSerializer(data=self.payload(category, vendor))
        assert s.is_valid(), s.errors

    def test_perishable_with_shelf_life_ok(self, category, vendor):
        s = ProductSerializer(data=self.payload(category, vendor, is_perishable=True, shelf_life_days=7))
        assert s.is_valid(), s.errors

    def test_perishable_without_shelf_life_ok(self, category, vendor):
        s = ProductSerializer(data=self.payload(category, vendor, is_perishable=True))
        assert s.is_valid(), s.errors

    def test_negative_shelf_life(self, category, vendor):
        s = ProductSerializer(data=self.payload(category, vendor, is_perishable=True, shelf_life_days=-1))
        assert not s.is_valid()
        assert "shelf_life_days" in s.errors

    def test_shelf_life_on_non_perishable(self, category, vendor):
        s = ProductSerializer(data=self.payload(category, vendor, is_perishable=False, shelf_life_days=5))
        assert not s.is_valid()
        assert "shelf_life_days" in s.errors

    def test_partial_update_uses_existing_is_perishable(self, make_product):
        p = make_product(is_perishable=True)
        s = ProductSerializer(p, data={"shelf_life_days": 3}, partial=True)
        assert s.is_valid(), s.errors

    def test_partial_update_on_non_perishable_instance_rejected(self, product):
        s = ProductSerializer(product, data={"shelf_life_days": 3}, partial=True)
        assert not s.is_valid()

    def test_partial_update_without_shelf_life_fields(self, product):
        s = ProductSerializer(product, data={"name": "Renamed"}, partial=True)
        assert s.is_valid(), s.errors

    def test_nested_and_derived_fields(self, make_product, make_brand, make_attribute):
        brand = make_brand(name="Acme")
        p = make_product(brand=brand)
        ProductVariant.objects.create(
            product=p, name="v", sku="V-X", size_value=Decimal("1"), size_unit="kg", selling_price=Decimal("2")
        )
        ProductAttributeValue.objects.create(product=p, attribute=make_attribute(name="Origin"), value="Rwanda")
        data = ProductSerializer(p).data
        assert data["category_name"] == p.category.name
        assert data["brand_name"] == "Acme"
        assert data["vendor_name"]
        assert len(data["variants"]) == 1
        assert data["variants"][0]["product_name"] == p.name
        assert data["attribute_values"][0]["attribute_name"] == "Origin"
        assert data["images"] == []

    def test_brand_name_none_when_no_brand(self, product):
        assert ProductSerializer(product).data["brand_name"] is None

    def test_duplicate_sku_rejected(self, product, category, vendor):
        s = ProductSerializer(data=self.payload(category, vendor, sku=product.sku))
        assert not s.is_valid()
        assert "sku" in s.errors

    def test_missing_required_fields(self):
        s = ProductSerializer(data={})
        assert not s.is_valid()
        assert {"name", "slug", "sku", "category", "vendor", "base_price"} <= set(s.errors)


class TestOtherSerializers:
    def test_variant_serializer(self, product, make_variant):
        data = ProductVariantSerializer(make_variant()).data
        assert data["product_name"] == product.name
        assert Decimal(data["selling_price"]) == Decimal("4.50")

    def test_variant_required_fields(self):
        s = ProductVariantSerializer(data={})
        assert not s.is_valid()
        assert {"product", "name", "sku", "size_value", "size_unit", "selling_price"} <= set(s.errors)

    def test_attribute_serializer_fields(self, make_attribute):
        data = ProductAttributeSerializer(make_attribute()).data
        assert set(data) == {"id", "name", "description"}

    def test_attribute_value_serializer(self, product, make_attribute):
        attr = make_attribute(name="Grade")
        val = ProductAttributeValue.objects.create(product=product, attribute=attr, value="A")
        data = ProductAttributeValueSerializer(val).data
        assert data["attribute_name"] == "Grade"
        assert data["value"] == "A"

    def test_attribute_value_duplicate_pair_rejected(self, product, make_attribute):
        attr = make_attribute()
        ProductAttributeValue.objects.create(product=product, attribute=attr, value="A")
        s = ProductAttributeValueSerializer(data={"product": product.pk, "attribute": attr.pk, "value": "B"})
        assert not s.is_valid()

    def test_image_serializer_fields(self, product):
        img = ProductImage.objects.create(product=product, image="product_images/a.jpg", alt_text="x")
        data = ProductImageSerializer(img).data
        assert set(data) == {"id", "product", "image", "alt_text", "is_primary", "display_order"}


# ---------------------------------------------------------------------------
# Permissions (CatalogPermission) across every viewset
# ---------------------------------------------------------------------------
class TestCatalogPermission:
    @pytest.mark.parametrize("viewset", ALL_VIEWSETS)
    def test_anonymous_can_read(self, call, viewset):
        assert call(viewset, "list").status_code == 200

    @pytest.mark.parametrize("viewset", ALL_VIEWSETS)
    def test_anonymous_cannot_write(self, call, viewset):
        assert call(viewset, "create", data={}).status_code in (401, 403)

    @pytest.mark.parametrize("viewset", ALL_VIEWSETS)
    def test_customer_cannot_write(self, call, customer, viewset):
        assert call(viewset, "create", user=customer, data={}).status_code == 403

    def test_customer_cannot_update_or_delete(self, call, customer, category):
        assert call(CategoryViewSet, "partial_update", user=customer, pk=category.pk, data={"name": "x"}).status_code == 403
        assert call(CategoryViewSet, "update", user=customer, pk=category.pk, data={"name": "x"}).status_code == 403
        assert call(CategoryViewSet, "destroy", user=customer, pk=category.pk).status_code == 403
        assert Category.objects.filter(pk=category.pk, name=category.name).exists()

    def test_anonymous_cannot_delete(self, call, category):
        assert call(CategoryViewSet, "destroy", pk=category.pk).status_code in (401, 403)
        assert Category.objects.filter(pk=category.pk).exists()

    def test_customer_can_read(self, call, customer):
        assert call(CategoryViewSet, "list", user=customer).status_code == 200


# ---------------------------------------------------------------------------
# CategoryViewSet
# ---------------------------------------------------------------------------
class TestCategoryViewSet:
    def test_anonymous_sees_only_active(self, call, make_category):
        active = make_category()
        make_category(is_active=False)
        assert ids(call(CategoryViewSet, "list")) == [str(active.pk)]

    def test_staff_sees_inactive_too(self, call, staff, make_category):
        make_category()
        make_category(is_active=False)
        assert len(rows(call(CategoryViewSet, "list", user=staff))) == 2

    def test_inactive_category_hidden_on_retrieve(self, call, staff, make_category):
        hidden = make_category(is_active=False)
        assert call(CategoryViewSet, "retrieve", pk=hidden.pk).status_code == 404
        assert call(CategoryViewSet, "retrieve", user=staff, pk=hidden.pk).status_code == 200

    def test_ordering(self, call, make_category):
        c = make_category(name="C", display_order=2)
        a = make_category(name="A", display_order=1)
        b = make_category(name="B", display_order=1)
        assert ids(call(CategoryViewSet, "list")) == [str(a.pk), str(b.pk), str(c.pk)]

    def test_filter_parent_null(self, call, make_category):
        root = make_category()
        make_category(parent=root)
        assert ids(call(CategoryViewSet, "list", query={"parent": "null"})) == [str(root.pk)]

    def test_filter_by_parent_id(self, call, make_category):
        root = make_category()
        child = make_category(parent=root)
        make_category()
        assert ids(call(CategoryViewSet, "list", query={"parent": root.pk})) == [str(child.pk)]

    def test_retrieve_includes_active_subcategories(self, call, make_category):
        parent = make_category()
        active = make_category(parent=parent)
        make_category(parent=parent, is_active=False)
        resp = call(CategoryViewSet, "retrieve", pk=parent.pk)
        assert [c["id"] for c in resp.data["subcategories"]] == [active.pk]

    def test_staff_create(self, call, staff):
        resp = call(CategoryViewSet, "create", user=staff, data={"name": "Fruit", "slug": "fruit"})
        assert resp.status_code == 201
        assert Category.objects.get(slug="fruit").display_order == 0

    def test_create_duplicate_slug(self, call, staff, category):
        resp = call(CategoryViewSet, "create", user=staff, data={"name": "Other", "slug": category.slug})
        assert resp.status_code == 400

    def test_create_requires_name_and_slug(self, call, staff):
        assert call(CategoryViewSet, "create", user=staff, data={}).status_code == 400

    def test_staff_patch(self, call, staff, category):
        resp = call(CategoryViewSet, "partial_update", user=staff, pk=category.pk, data={"name": "Renamed"})
        assert resp.status_code == 200
        category.refresh_from_db()
        assert category.name == "Renamed"

    def test_staff_delete(self, call, staff, category):
        assert call(CategoryViewSet, "destroy", user=staff, pk=category.pk).status_code == 204
        assert not Category.objects.filter(pk=category.pk).exists()

    def test_delete_category_with_products_is_blocked(self, call, staff, category, product):
        """
        Documents current behaviour: the PROTECT error is not handled, so it propagates
        (a 500 in production). If you add handling that returns 409/400, update this test.
        """
        with pytest.raises(ProtectedError):
            call(CategoryViewSet, "destroy", user=staff, pk=category.pk)
        assert Category.objects.filter(pk=category.pk).exists()


# ---------------------------------------------------------------------------
# BrandViewSet
# ---------------------------------------------------------------------------
class TestBrandViewSet:
    def test_visibility_by_role(self, call, staff, make_brand):
        active = make_brand()
        make_brand(is_active=False)
        assert ids(call(BrandViewSet, "list")) == [str(active.pk)]
        assert len(rows(call(BrandViewSet, "list", user=staff))) == 2

    def test_ordered_by_name(self, call, make_brand):
        z = make_brand(name="Zeta")
        a = make_brand(name="Alpha")
        assert ids(call(BrandViewSet, "list")) == [str(a.pk), str(z.pk)]

    def test_staff_crud(self, call, staff):
        created = call(BrandViewSet, "create", user=staff, data={"name": "Acme"})
        assert created.status_code == 201
        pk = created.data["id"]
        assert call(BrandViewSet, "partial_update", user=staff, pk=pk, data={"name": "Acme Ltd"}).status_code == 200
        assert Brand.objects.get(pk=pk).name == "Acme Ltd"
        assert call(BrandViewSet, "destroy", user=staff, pk=pk).status_code == 204

    def test_deleting_brand_keeps_products(self, call, staff, make_product, make_brand):
        brand = make_brand()
        p = make_product(brand=brand)
        call(BrandViewSet, "destroy", user=staff, pk=brand.pk)
        p.refresh_from_db()
        assert p.brand is None

    def test_name_required(self, call, staff):
        assert call(BrandViewSet, "create", user=staff, data={}).status_code == 400


# ---------------------------------------------------------------------------
# ProductViewSet
# ---------------------------------------------------------------------------
class TestProductViewSet:
    def payload(self, category, vendor, **overrides):
        data = {
            "name": "Mango",
            "slug": "mango",
            "sku": "MANGO-1",
            "category": category.pk,
            "vendor": vendor.pk,
            "base_price": "3.50",
        }
        data.update(overrides)
        return data

    # -- visibility -----------------------------------------------------------
    def test_anonymous_hides_unavailable_and_inactive_category(self, call, make_product, make_category):
        visible = make_product()
        make_product(is_available=False)
        make_product(category=make_category(is_active=False))
        assert ids(call(ProductViewSet, "list")) == [str(visible.pk)]

    def test_staff_sees_everything(self, call, staff, make_product, make_category):
        make_product()
        make_product(is_available=False)
        make_product(category=make_category(is_active=False))
        assert len(rows(call(ProductViewSet, "list", user=staff))) == 3

    def test_unavailable_product_404_for_public(self, call, staff, make_product):
        p = make_product(is_available=False)
        assert call(ProductViewSet, "retrieve", pk=p.pk).status_code == 404
        assert call(ProductViewSet, "retrieve", user=staff, pk=p.pk).status_code == 200

    # -- ordering / filters -----------------------------------------------------
    def test_newest_first(self, call, make_product):
        old, new = make_product(), make_product()
        backdate(Product, old, "created_at", 60)
        backdate(Product, new, "created_at", 1)
        assert ids(call(ProductViewSet, "list")) == [str(new.pk), str(old.pk)]

    def test_search_by_name_sku_description(self, call, make_product):
        by_name = make_product(name="Golden Pineapple")
        by_sku = make_product(sku="ZZZ-999")
        by_desc = make_product(description="sweet and tropical")
        make_product(name="Other")
        assert ids(call(ProductViewSet, "list", query={"search": "pineapple"})) == [str(by_name.pk)]
        assert ids(call(ProductViewSet, "list", query={"search": "zzz-999"})) == [str(by_sku.pk)]
        assert ids(call(ProductViewSet, "list", query={"search": "TROPICAL"})) == [str(by_desc.pk)]

    def test_filter_by_category_id_and_slug(self, call, make_product, make_category):
        other = make_category(slug="other-cat")
        p = make_product(category=other)
        make_product()
        assert ids(call(ProductViewSet, "list", query={"category": other.pk})) == [str(p.pk)]
        assert ids(call(ProductViewSet, "list", query={"category_slug": "other-cat"})) == [str(p.pk)]

    def test_filter_by_brand(self, call, make_product, make_brand):
        brand = make_brand()
        p = make_product(brand=brand)
        make_product()
        assert ids(call(ProductViewSet, "list", query={"brand": brand.pk})) == [str(p.pk)]

    def test_filter_by_vendor(self, call, make_product, make_vendor):
        other_vendor = make_vendor()
        p = make_product(vendor=other_vendor)
        make_product()
        assert ids(call(ProductViewSet, "list", query={"vendor": other_vendor.pk})) == [str(p.pk)]

    @pytest.mark.parametrize("field", ["is_featured", "is_perishable"])
    def test_boolean_filters(self, call, make_product, field):
        yes = make_product(**{field: True})
        no = make_product()
        assert ids(call(ProductViewSet, "list", query={field: "true"})) == [str(yes.pk)]
        assert ids(call(ProductViewSet, "list", query={field: "TRUE"})) == [str(yes.pk)]
        assert ids(call(ProductViewSet, "list", query={field: "false"})) == [str(no.pk)]

    def test_filters_combine(self, call, make_product):
        make_product(name="Red Apple", is_featured=True)
        target = make_product(name="Red Pepper", is_featured=True)
        make_product(name="Red Plum")
        resp = call(ProductViewSet, "list", query={"search": "pepper", "is_featured": "true"})
        assert ids(resp) == [str(target.pk)]

    # -- retrieve / efficiency ----------------------------------------------------
    def test_retrieve_with_nested_data(self, call, product, make_variant, make_attribute):
        make_variant()
        ProductAttributeValue.objects.create(product=product, attribute=make_attribute(name="Origin"), value="Kenya")
        resp = call(ProductViewSet, "retrieve", pk=product.pk)
        assert resp.status_code == 200
        assert len(resp.data["variants"]) == 1
        assert resp.data["attribute_values"][0]["attribute_name"] == "Origin"

    def test_list_query_count_is_constant(self, call, make_product, make_attribute, django_assert_max_num_queries):
        attr = make_attribute()
        for i in range(5):
            p = make_product()
            ProductVariant.objects.create(
                product=p, name="v", sku=f"Q-{i}", size_value=Decimal("1"), size_unit="kg", selling_price=Decimal("2")
            )
            ProductAttributeValue.objects.create(product=p, attribute=attr, value="x")
        with django_assert_max_num_queries(6):
            resp = call(ProductViewSet, "list")
            assert resp.status_code == 200
            _ = rows(resp)

    # -- writes -------------------------------------------------------------------
    def test_staff_create(self, call, staff, category, vendor):
        resp = call(ProductViewSet, "create", user=staff, data=self.payload(category, vendor))
        assert resp.status_code == 201
        p = Product.objects.get(sku="MANGO-1")
        assert p.base_price == Decimal("3.50")
        assert p.is_available is True

    def test_create_perishable_with_shelf_life(self, call, staff, category, vendor):
        resp = call(
            ProductViewSet,
            "create",
            user=staff,
            data=self.payload(category, vendor, is_perishable=True, shelf_life_days=7),
        )
        assert resp.status_code == 201
        assert Product.objects.get().shelf_life_days == 7

    def test_create_negative_shelf_life(self, call, staff, category, vendor):
        resp = call(
            ProductViewSet,
            "create",
            user=staff,
            data=self.payload(category, vendor, is_perishable=True, shelf_life_days=-2),
        )
        assert resp.status_code == 400
        assert "shelf_life_days" in resp.data

    def test_create_shelf_life_on_non_perishable(self, call, staff, category, vendor):
        resp = call(ProductViewSet, "create", user=staff, data=self.payload(category, vendor, shelf_life_days=3))
        assert resp.status_code == 400

    def test_create_duplicate_sku_or_slug(self, call, staff, product, category, vendor):
        assert call(ProductViewSet, "create", user=staff, data=self.payload(category, vendor, sku=product.sku)).status_code == 400
        assert call(ProductViewSet, "create", user=staff, data=self.payload(category, vendor, slug=product.slug)).status_code == 400

    def test_create_missing_fields(self, call, staff):
        assert call(ProductViewSet, "create", user=staff, data={"name": "x"}).status_code == 400

    def test_create_invalid_price(self, call, staff, category, vendor):
        resp = call(ProductViewSet, "create", user=staff, data=self.payload(category, vendor, base_price="abc"))
        assert resp.status_code == 400

    def test_staff_patch(self, call, staff, product):
        resp = call(ProductViewSet, "partial_update", user=staff, pk=product.pk, data={"base_price": "99.00"})
        assert resp.status_code == 200
        product.refresh_from_db()
        assert product.base_price == Decimal("99.00")

    def test_staff_delete_cascades_variants(self, call, staff, product, make_variant):
        make_variant()
        assert call(ProductViewSet, "destroy", user=staff, pk=product.pk).status_code == 204
        assert ProductVariant.objects.count() == 0


# ---------------------------------------------------------------------------
# ProductVariantViewSet
# ---------------------------------------------------------------------------
class TestProductVariantViewSet:
    def payload(self, product, **overrides):
        data = {
            "product": str(product.pk),
            "name": "1kg bag",
            "sku": "VAR-NEW",
            "size_value": "1",
            "size_unit": "kg",
            "selling_price": "7.25",
        }
        data.update(overrides)
        return data

    def test_public_sees_only_active_variants_of_visible_products(self, call, make_variant, make_product, make_category):
        visible = make_variant()
        make_variant(is_active=False)
        hidden_product = make_product(is_available=False)
        make_variant(product=hidden_product)
        inactive_cat_product = make_product(category=make_category(is_active=False))
        make_variant(product=inactive_cat_product)
        assert ids(call(ProductVariantViewSet, "list")) == [str(visible.pk)]

    def test_staff_sees_all(self, call, staff, make_variant):
        make_variant()
        make_variant(is_active=False)
        assert len(rows(call(ProductVariantViewSet, "list", user=staff))) == 2

    def test_filter_by_product(self, call, make_variant, make_product):
        other = make_product()
        v = make_variant(product=other)
        make_variant()
        assert ids(call(ProductVariantViewSet, "list", query={"product": str(other.pk)})) == [str(v.pk)]

    def test_ordering_by_product_name_then_variant_name(self, call, make_product, make_variant):
        p_b = make_product(name="B product")
        p_a = make_product(name="A product")
        v1 = make_variant(product=p_b, name="a")
        v2 = make_variant(product=p_a, name="z")
        v3 = make_variant(product=p_a, name="b")
        assert ids(call(ProductVariantViewSet, "list")) == [str(v3.pk), str(v2.pk), str(v1.pk)]

    def test_staff_create(self, call, staff, product):
        resp = call(ProductVariantViewSet, "create", user=staff, data=self.payload(product))
        assert resp.status_code == 201
        assert resp.data["product_name"] == product.name
        assert ProductVariant.objects.get(sku="VAR-NEW").selling_price == Decimal("7.25")

    def test_create_duplicate_sku(self, call, staff, product, make_variant):
        v = make_variant()
        resp = call(ProductVariantViewSet, "create", user=staff, data=self.payload(product, sku=v.sku))
        assert resp.status_code == 400

    def test_create_unknown_product(self, call, staff):
        resp = call(
            ProductVariantViewSet,
            "create",
            user=staff,
            data={
                "product": "00000000-0000-0000-0000-000000000000",
                "name": "x",
                "sku": "S",
                "size_value": "1",
                "size_unit": "kg",
                "selling_price": "1",
            },
        )
        assert resp.status_code == 400

    def test_staff_patch_and_delete(self, call, staff, make_variant):
        v = make_variant()
        assert call(ProductVariantViewSet, "partial_update", user=staff, pk=v.pk, data={"selling_price": "9.99"}).status_code == 200
        v.refresh_from_db()
        assert v.selling_price == Decimal("9.99")
        assert call(ProductVariantViewSet, "destroy", user=staff, pk=v.pk).status_code == 204


# ---------------------------------------------------------------------------
# ProductImageViewSet
# ---------------------------------------------------------------------------
class TestProductImageViewSet:
    def make(self, product, **kw):
        return ProductImage.objects.create(product=product, image="product_images/a.jpg", **kw)

    def test_public_hides_images_of_unavailable_products(self, call, product, make_product):
        shown = self.make(product)
        self.make(make_product(is_available=False))
        assert ids(call(ProductImageViewSet, "list")) == [str(shown.pk)]

    def test_staff_sees_all(self, call, staff, product, make_product):
        self.make(product)
        self.make(make_product(is_available=False))
        assert len(rows(call(ProductImageViewSet, "list", user=staff))) == 2

    def test_filter_by_product_and_ordering(self, call, product, make_product):
        second = self.make(product, display_order=2)
        first = self.make(product, display_order=1)
        self.make(make_product())
        resp = call(ProductImageViewSet, "list", query={"product": str(product.pk)})
        assert ids(resp) == [str(first.pk), str(second.pk)]

    def test_staff_upload(self, call, staff, product, media):
        resp = call(
            ProductImageViewSet,
            "create",
            user=staff,
            data={"product": str(product.pk), "image": png_upload(), "alt_text": "front", "is_primary": "true"},
            fmt="multipart",
        )
        assert resp.status_code == 201, resp.data
        img = ProductImage.objects.get()
        assert img.is_primary is True
        assert img.alt_text == "front"

    def test_upload_requires_image(self, call, staff, product):
        resp = call(ProductImageViewSet, "create", user=staff, data={"product": str(product.pk)})
        assert resp.status_code == 400

    def test_upload_rejects_non_image(self, call, staff, product, media):
        fake = SimpleUploadedFile("note.txt", b"not an image", content_type="text/plain")
        resp = call(
            ProductImageViewSet, "create", user=staff, data={"product": str(product.pk), "image": fake}, fmt="multipart"
        )
        assert resp.status_code == 400

    def test_staff_delete(self, call, staff, product):
        img = self.make(product)
        assert call(ProductImageViewSet, "destroy", user=staff, pk=img.pk).status_code == 204


# ---------------------------------------------------------------------------
# ProductAttributeViewSet
# ---------------------------------------------------------------------------
class TestProductAttributeViewSet:
    def test_list_ordered_by_name(self, call, make_attribute):
        z = make_attribute(name="Zone")
        a = make_attribute(name="Age")
        assert ids(call(ProductAttributeViewSet, "list")) == [str(a.pk), str(z.pk)]

    def test_staff_create(self, call, staff):
        resp = call(ProductAttributeViewSet, "create", user=staff, data={"name": "Color", "description": "Shade"})
        assert resp.status_code == 201
        assert ProductAttribute.objects.get(name="Color").description == "Shade"

    def test_duplicate_name(self, call, staff, make_attribute):
        attr = make_attribute()
        resp = call(ProductAttributeViewSet, "create", user=staff, data={"name": attr.name})
        assert resp.status_code == 400

    def test_name_required(self, call, staff):
        assert call(ProductAttributeViewSet, "create", user=staff, data={}).status_code == 400

    def test_staff_patch_and_delete(self, call, staff, make_attribute):
        attr = make_attribute()
        assert call(ProductAttributeViewSet, "partial_update", user=staff, pk=attr.pk, data={"name": "New"}).status_code == 200
        assert call(ProductAttributeViewSet, "destroy", user=staff, pk=attr.pk).status_code == 204


# ---------------------------------------------------------------------------
# ProductAttributeValueViewSet
# ---------------------------------------------------------------------------
class TestProductAttributeValueViewSet:
    def make(self, product, attribute, value="x"):
        return ProductAttributeValue.objects.create(product=product, attribute=attribute, value=value)

    def test_public_hides_values_of_unavailable_products(self, call, product, make_product, make_attribute):
        attr = make_attribute()
        shown = self.make(product, attr)
        self.make(make_product(is_available=False), attr)
        assert ids(call(ProductAttributeValueViewSet, "list")) == [str(shown.pk)]

    def test_staff_sees_all(self, call, staff, product, make_product, make_attribute):
        attr = make_attribute()
        self.make(product, attr)
        self.make(make_product(is_available=False), attr)
        assert len(rows(call(ProductAttributeValueViewSet, "list", user=staff))) == 2

    def test_filter_by_product_and_attribute(self, call, product, make_product, make_attribute):
        color, size = make_attribute(name="Color"), make_attribute(name="Size")
        other = make_product()
        target = self.make(product, color)
        self.make(product, size)
        self.make(other, color)
        resp = call(
            ProductAttributeValueViewSet, "list", query={"product": str(product.pk), "attribute": str(color.pk)}
        )
        assert ids(resp) == [str(target.pk)]

    def test_ordered_by_attribute_name(self, call, product, make_attribute):
        z = self.make(product, make_attribute(name="Zone"))
        a = self.make(product, make_attribute(name="Age"))
        assert ids(call(ProductAttributeValueViewSet, "list")) == [str(a.pk), str(z.pk)]

    def test_staff_create(self, call, staff, product, make_attribute):
        attr = make_attribute()
        resp = call(
            ProductAttributeValueViewSet,
            "create",
            user=staff,
            data={"product": str(product.pk), "attribute": str(attr.pk), "value": "Red"},
        )
        assert resp.status_code == 201
        assert resp.data["attribute_name"] == attr.name

    def test_duplicate_attribute_for_product(self, call, staff, product, make_attribute):
        attr = make_attribute()
        self.make(product, attr, "Red")
        resp = call(
            ProductAttributeValueViewSet,
            "create",
            user=staff,
            data={"product": str(product.pk), "attribute": str(attr.pk), "value": "Blue"},
        )
        assert resp.status_code == 400

    def test_value_required(self, call, staff, product, make_attribute):
        resp = call(
            ProductAttributeValueViewSet,
            "create",
            user=staff,
            data={"product": str(product.pk), "attribute": str(make_attribute().pk)},
        )
        assert resp.status_code == 400

    def test_staff_patch_and_delete(self, call, staff, product, make_attribute):
        val = self.make(product, make_attribute(), "Red")
        assert call(ProductAttributeValueViewSet, "partial_update", user=staff, pk=val.pk, data={"value": "Blue"}).status_code == 200
        val.refresh_from_db()
        assert val.value == "Blue"
        assert call(ProductAttributeValueViewSet, "destroy", user=staff, pk=val.pk).status_code == 204