
from rest_framework.routers import DefaultRouter

from .views import (
    CouponViewSet,
    CouponUsageViewSet,
    PromotionViewSet,
)

router = DefaultRouter()

router.register(
    r"coupons",
    CouponViewSet,
    basename="coupon"
)

router.register(
    r"coupon-usages",
    CouponUsageViewSet,
    basename="coupon-usage"
)

router.register(
    r"promotions",
    PromotionViewSet,
    basename="promotion"
)

urlpatterns = router.urls
