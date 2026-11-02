from django.contrib import admin
from django.http import JsonResponse
from importlib import import_module
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

try:
    spectacular_views = import_module("drf_spectacular.views")
except ModuleNotFoundError as exc:
    if exc.name != "drf_spectacular":
        raise
    spectacular_views = None

def home(request):
    return JsonResponse({"message": "IsokoGo API is running"})


def schema_unavailable(request):
    return JsonResponse(
        {"error": "API schema documentation is unavailable"}, status=503
    )

urlpatterns = [
    path('', home),
    path("admin/", admin.site.urls),

    # Application APIs
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/analytics/", include("apps.analytics.urls")),
    path("api/carts/", include("apps.carts.urls")),
    path("api/catalog/", include("apps.catalog.urls")),
    path("api/customers/", include("apps.customers.urls")),
    path("api/deliveries/", include("apps.deliveries.urls")),
    path("api/inventory/", include("apps.inventory.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/payments/", include("apps.payments.urls")),
    path("api/promotions/", include("apps.promotions.urls")),
    path("api/reviews/", include("apps.reviews.urls")),
    path("api/support/", include("apps.support.urls")),
    path("api/vendors/", include("apps.vendors.urls")),

    # API documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]
