from datetime import timedelta

from django.db.models import Count, Prefetch
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    ClimateLog,
    Greenhouse,
    IrrigationCycle,
    IrrigationDurationRevision,
    Zone,
)
from .serializers import (
    ClimateLogSerializer,
    GreenhouseSerializer,
    IrrigationCycleSerializer,
    IrrigationDurationRevisionSerializer,
    ZoneSerializer,
)


class GreenhouseViewSet(viewsets.ModelViewSet):
    queryset = Greenhouse.objects.annotate(zone_count=Count("zones")).all()
    serializer_class = GreenhouseSerializer


class ZoneViewSet(viewsets.ModelViewSet):
    serializer_class = ZoneSerializer

    def get_queryset(self):
        qs = Zone.objects.select_related("greenhouse").all()
        greenhouse_id = self.request.query_params.get("greenhouseId")
        status = self.request.query_params.get("status")
        if greenhouse_id:
            qs = qs.filter(greenhouse_id=greenhouse_id)
        if status:
            qs = qs.filter(status=status)
        return qs


class ClimateLogViewSet(viewsets.ModelViewSet):
    serializer_class = ClimateLogSerializer

    def get_queryset(self):
        qs = ClimateLog.objects.select_related("zone", "zone__greenhouse").all()
        zone_id = self.request.query_params.get("zoneId")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        return qs


class IrrigationCycleViewSet(viewsets.ModelViewSet):
    serializer_class = IrrigationCycleSerializer

    def get_queryset(self):
        qs = (
            IrrigationCycle.objects.select_related("zone", "zone__greenhouse")
            .annotate(revision_count=Count("duration_revisions"))
            .prefetch_related(
                Prefetch(
                    "duration_revisions",
                    queryset=IrrigationDurationRevision.objects.order_by(
                        "-revised_at", "-id"
                    ),
                )
            )
            .all()
        )
        zone_id = self.request.query_params.get("zoneId")
        status = self.request.query_params.get("status")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        if status:
            qs = qs.filter(status=status)
        return qs

    @action(detail=True, methods=["get"])
    def revisions(self, request, pk=None):
        """单条轮灌的时长修订留痕列表（新→旧）。"""
        cycle = self.get_object()
        serializer = IrrigationDurationRevisionSerializer(
            cycle.duration_revisions.all(), many=True
        )
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="duration-audit")
    def duration_audit(self, request):
        """时长稽核：有留痕的轮灌条数（与列表中 revisionCount>0 的行数一致）。"""
        count = (
            IrrigationCycle.objects.filter(duration_revisions__isnull=False)
            .distinct()
            .count()
        )
        return Response({"cyclesWithRevisions": count})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    now = timezone.now()
    since_24h = now - timedelta(hours=24)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    data = {
        "greenhouseCount": Greenhouse.objects.count(),
        "growingZoneCount": Zone.objects.filter(status=Zone.STATUS_GROWING).count(),
        "climateLogLast24h": ClimateLog.objects.filter(
            recorded_at__gte=since_24h
        ).count(),
        "irrigationScheduledToday": IrrigationCycle.objects.filter(
            status=IrrigationCycle.STATUS_SCHEDULED,
            start_at__gte=today_start,
            start_at__lt=today_end,
        ).count(),
    }
    return Response(data)
