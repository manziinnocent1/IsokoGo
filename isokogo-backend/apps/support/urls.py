
from rest_framework.routers import DefaultRouter

from .views import SupportTicketViewSet

router = DefaultRouter()

router.register(
    r"tickets",
    SupportTicketViewSet,
    basename="support-ticket",
)

urlpatterns = router.urls
