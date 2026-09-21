from datetime import timedelta

from django.db import transaction
from django.db.models import Count, OuterRef, Subquery
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ClimateLog, DurationRevision, Greenhouse, IrrigationCycle, Zone
from .serializers import (
    ClimateLogSerializer,
    DurationRevisionSerializer,
    GreenhouseSerializer,
    IrrigationCycleSerializer,
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
        # 最新时长取最新一条留痕的新分钟（按修订时刻倒序），无留痕时回退为当前时长。
        latest_new_min = Subquery(
            DurationRevision.objects.filter(cycle_id=OuterRef("pk"))
            .order_by("-revised_at", "-id")
            .values("new_min")[:1]
        )
        qs = (
            IrrigationCycle.objects.select_related("zone", "zone__greenhouse")
            .annotate(
                revision_count=Count("duration_revisions", distinct=True),
                latest_revision_new_min=latest_new_min,
            )
        )
        zone_id = self.request.query_params.get("zoneId")
        cycle_status = self.request.query_params.get("status")
        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        if cycle_status:
            qs = qs.filter(status=cycle_status)
        return qs

    @action(detail=True, methods=["post"], url_path="revise-duration")
    def revise_duration(self, request, pk=None):
        """修改轮灌时长：校验原因/新值后，同事务更新时长并插入一条修订留痕。

        任一条件不满足或留痕缺失，均返回 400 且时长保持原值。
        """
        cycle = self.get_object()

        raw_new_min = request.data.get("newMin")
        try:
            if isinstance(raw_new_min, bool) or (
                isinstance(raw_new_min, float) and not raw_new_min.is_integer()
            ):
                raise ValueError
            new_min = int(raw_new_min)
        except (TypeError, ValueError):
            return Response(
                {"newMin": "新分钟必须为正整数"}, status=status.HTTP_400_BAD_REQUEST
            )
        if new_min <= 0:
            return Response(
                {"newMin": "新分钟必须为正整数"}, status=status.HTTP_400_BAD_REQUEST
            )

        reason = str(request.data.get("reason") or "").strip()
        if len(reason) < 8:
            return Response(
                {"reason": "修订原因去空白后长度至少 8 个字符"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_min = cycle.duration_min
        if new_min == old_min:
            return Response(
                {"newMin": "新分钟必须与原分钟不同"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            cycle.duration_min = new_min
            cycle.save(update_fields=["duration_min", "updated_at"])
            revision = DurationRevision.objects.create(
                cycle=cycle,
                old_min=old_min,
                new_min=new_min,
                reason=reason,
            )
            # 缺留痕则 400：留痕不存在时整个事务回滚，时长保持原值。
            if not DurationRevision.objects.filter(pk=revision.pk).exists():
                transaction.set_rollback(True)
                return Response(
                    {"detail": "缺少时长修订留痕，已拒绝本次修改"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        cycle = self.get_queryset().get(pk=cycle.pk)
        return Response(
            {
                "cycle": IrrigationCycleSerializer(
                    cycle, context=self.get_serializer_context()
                ).data,
                "revision": DurationRevisionSerializer(revision).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def revisions(self, request, pk=None):
        """该轮灌的时长修订留痕列表（最新一条在前）。"""
        cycle = self.get_object()
        qs = cycle.duration_revisions.all()
        return Response(DurationRevisionSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def irrigation_duration_audit(request):
    """时长稽核：存在修订留痕的轮灌条数。

    该数与列表接口中 revisionCount > 0 的行数相等。
    """
    revised_cycle_count = IrrigationCycle.objects.exclude(
        duration_revisions__isnull=True
    ).count()
    return Response({"revisedCycleCount": revised_cycle_count})


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
