"""
Pytest tests for the analytics app (model, serializer, viewset).

Requirements:
    pip install pytest pytest-django

The viewset is called directly with APIRequestFactory, so these tests do not
depend on your urls.py. They authenticate with whatever AUTH_USER_MODEL you use;
adjust the `user` fixture if your create_user needs extra required fields.
"""
import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from .models import Analytics
from .serializers import AnalyticsSerializer
from .views import AnalyticsViewSet

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        email="analyst@example.com",
        password="Tr0ub4dor&Zebra-Lamp-92",
    )


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def call(factory):
    """call("list" | "create" | "retrieve" | "update" | "partial_update" | "destroy", user=u, pk=..., data=...)"""
    methods = {
        "list": ("get", {"get": "list"}),
        "create": ("post", {"post": "create"}),
        "retrieve": ("get", {"get": "retrieve"}),
        "update": ("put", {"put": "update"}),
        "partial_update": ("patch", {"patch": "partial_update"}),
        "destroy": ("delete", {"delete": "destroy"}),
    }

    def _call(action, user=None, pk=None, data=None):
        http_method, mapping = methods[action]
        make = getattr(factory, http_method)
        if http_method in ("post", "put", "patch"):
            request = make("/analytics/", data or {}, format="json")
        else:
            request = make("/analytics/")
        if user is not None:
            force_authenticate(request, user=user)
        kwargs = {"pk": str(pk)} if pk is not None else {}
        return AnalyticsViewSet.as_view(mapping)(request, **kwargs)

    return _call


@pytest.fixture
def make_analytics():
    def _make(minutes_ago=0, **kwargs):
        obj = Analytics.objects.create(**kwargs)
        # auto_now_add can't be set on create, so backdate with update().
        Analytics.objects.filter(pk=obj.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))
        obj.refresh_from_db()
        return obj

    return _make


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class TestAnalyticsModel:
    def test_uuid_primary_key_generated(self):
        obj = Analytics.objects.create()
        assert isinstance(obj.pk, uuid.UUID)

    def test_each_record_gets_unique_id(self):
        a, b = Analytics.objects.create(), Analytics.objects.create()
        assert a.pk != b.pk

    def test_timestamps_set_on_create(self):
        obj = Analytics.objects.create()
        assert obj.created_at is not None
        assert obj.updated_at is not None

    def test_resolved_at_defaults_to_none(self):
        assert Analytics.objects.create().resolved_at is None

    def test_resolved_at_can_be_set(self):
        now = timezone.now()
        obj = Analytics.objects.create(resolved_at=now)
        obj.refresh_from_db()
        assert obj.resolved_at == now

    def test_updated_at_changes_on_save_but_created_at_does_not(self):
        obj = Analytics.objects.create()
        created, updated = obj.created_at, obj.updated_at
        obj.resolved_at = timezone.now()
        obj.save()
        obj.refresh_from_db()
        assert obj.created_at == created
        assert obj.updated_at >= updated

    def test_str_is_id(self):
        obj = Analytics.objects.create()
        assert str(obj) == str(obj.pk)

    def test_default_ordering_newest_first(self, make_analytics):
        old = make_analytics(minutes_ago=10)
        new = make_analytics(minutes_ago=1)
        assert list(Analytics.objects.all()) == [new, old]

    def test_meta(self):
        assert Analytics._meta.db_table == "analytics"
        assert Analytics._meta.verbose_name == "Analytics"
        assert Analytics._meta.verbose_name_plural == "Analytics"


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------
class TestAnalyticsSerializer:
    def test_fields(self):
        obj = Analytics.objects.create()
        data = AnalyticsSerializer(obj).data
        assert set(data) == {"id", "created_at", "updated_at", "resolved_at"}
        assert data["id"] == str(obj.pk)
        assert data["resolved_at"] is None

    def test_all_fields_read_only(self):
        s = AnalyticsSerializer()
        assert all(f.read_only for f in s.fields.values())

    def test_input_is_ignored(self):
        s = AnalyticsSerializer(
            data={
                "id": str(uuid.uuid4()),
                "created_at": "2000-01-01T00:00:00Z",
                "resolved_at": "2000-01-01T00:00:00Z",
            }
        )
        assert s.is_valid()
        assert s.validated_data == {}

    def test_many(self):
        Analytics.objects.create()
        Analytics.objects.create()
        assert len(AnalyticsSerializer(Analytics.objects.all(), many=True).data) == 2


# ---------------------------------------------------------------------------
# ViewSet: authentication
# ---------------------------------------------------------------------------
class TestAnalyticsViewSetAuth:
    @pytest.mark.parametrize("action", ["list", "create"])
    def test_collection_requires_auth(self, call, action):
        assert call(action).status_code in (401, 403)

    @pytest.mark.parametrize("action", ["retrieve", "update", "partial_update", "destroy"])
    def test_detail_requires_auth(self, call, action):
        obj = Analytics.objects.create()
        assert call(action, pk=obj.pk).status_code in (401, 403)

    def test_unauthenticated_delete_does_not_delete(self, call):
        obj = Analytics.objects.create()
        call("destroy", pk=obj.pk)
        assert Analytics.objects.filter(pk=obj.pk).exists()


# ---------------------------------------------------------------------------
# ViewSet: list / retrieve
# ---------------------------------------------------------------------------
class TestAnalyticsViewSetRead:
    def test_list_empty(self, call, user):
        resp = call("list", user=user)
        assert resp.status_code == 200
        assert list(resp.data) == []

    def test_list_newest_first(self, call, user, make_analytics):
        old = make_analytics(minutes_ago=30)
        mid = make_analytics(minutes_ago=15)
        new = make_analytics(minutes_ago=1)
        resp = call("list", user=user)
        assert resp.status_code == 200
        assert [row["id"] for row in resp.data] == [str(new.pk), str(mid.pk), str(old.pk)]

    def test_retrieve(self, call, user):
        obj = Analytics.objects.create()
        resp = call("retrieve", user=user, pk=obj.pk)
        assert resp.status_code == 200
        assert resp.data["id"] == str(obj.pk)

    def test_retrieve_unknown_id(self, call, user):
        assert call("retrieve", user=user, pk=uuid.uuid4()).status_code == 404

    def test_retrieve_malformed_id(self, call, user):
        assert call("retrieve", user=user, pk="not-a-uuid").status_code == 404


# ---------------------------------------------------------------------------
# ViewSet: create / update / delete
# ---------------------------------------------------------------------------
class TestAnalyticsViewSetWrite:
    def test_create(self, call, user):
        resp = call("create", user=user)
        assert resp.status_code == 201
        assert Analytics.objects.count() == 1
        assert resp.data["id"] == str(Analytics.objects.get().pk)
        assert resp.data["resolved_at"] is None

    def test_create_ignores_client_supplied_fields(self, call, user):
        fake_id = uuid.uuid4()
        resp = call(
            "create",
            user=user,
            data={"id": str(fake_id), "resolved_at": "2000-01-01T00:00:00Z", "created_at": "2000-01-01T00:00:00Z"},
        )
        assert resp.status_code == 201
        obj = Analytics.objects.get()
        assert obj.pk != fake_id
        assert obj.resolved_at is None
        assert obj.created_at.year != 2000

    def test_put_cannot_set_resolved_at(self, call, user):
        obj = Analytics.objects.create()
        resp = call("update", user=user, pk=obj.pk, data={"resolved_at": "2000-01-01T00:00:00Z"})
        assert resp.status_code == 200
        obj.refresh_from_db()
        assert obj.resolved_at is None

    def test_patch_cannot_set_resolved_at(self, call, user):
        obj = Analytics.objects.create()
        resp = call("partial_update", user=user, pk=obj.pk, data={"resolved_at": "2000-01-01T00:00:00Z"})
        assert resp.status_code == 200
        obj.refresh_from_db()
        assert obj.resolved_at is None

    def test_patch_cannot_clear_resolved_at(self, call, user):
        resolved = timezone.now()
        obj = Analytics.objects.create(resolved_at=resolved)
        call("partial_update", user=user, pk=obj.pk, data={"resolved_at": None})
        obj.refresh_from_db()
        assert obj.resolved_at == resolved

    def test_update_unknown_id(self, call, user):
        assert call("update", user=user, pk=uuid.uuid4()).status_code == 404

    def test_destroy(self, call, user):
        obj = Analytics.objects.create()
        resp = call("destroy", user=user, pk=obj.pk)
        assert resp.status_code == 204
        assert not Analytics.objects.filter(pk=obj.pk).exists()

    def test_destroy_unknown_id(self, call, user):
        assert call("destroy", user=user, pk=uuid.uuid4()).status_code == 404