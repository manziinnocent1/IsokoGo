
from rest_framework.routers import DefaultRouter

from .views import ProductReviewViewSet

router = DefaultRouter()

router.register(
    r"",
    ProductReviewViewSet,
    basename="product-review",
)

urlpatterns = router.urls
