from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ClimateLogViewSet,
    GreenhouseViewSet,
    IrrigationCycleViewSet,
    ZoneViewSet,
    dashboard_stats,
    irrigation_duration_audit,
)

router = DefaultRouter()
router.register("greenhouses", GreenhouseViewSet, basename="greenhouse")
router.register("zones", ZoneViewSet, basename="zone")
router.register("climate-logs", ClimateLogViewSet, basename="climate-log")
router.register("irrigation-cycles", IrrigationCycleViewSet, basename="irrigation-cycle")

urlpatterns = [
    path("dashboard/", dashboard_stats, name="dashboard"),
    path(
        "irrigation-duration-audit/",
        irrigation_duration_audit,
        name="irrigation-duration-audit",
    ),
    path("", include(router.urls)),
]
