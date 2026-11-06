
from rest_framework.routers import DefaultRouter

from .views import (
    VendorViewSet,
    VendorDocumentViewSet,
)

router = DefaultRouter()

router.register(
    r"vendors",
    VendorViewSet,
    basename="vendor",
)

router.register(
    r"documents",
    VendorDocumentViewSet,
    basename="vendor-document",
)

urlpatterns = router.urls
