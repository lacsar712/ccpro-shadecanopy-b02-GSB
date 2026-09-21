from django.db import transaction
from rest_framework import serializers

from .models import (
    ClimateLog,
    Greenhouse,
    IrrigationCycle,
    IrrigationDurationRevision,
    Zone,
)


class GreenhouseSerializer(serializers.ModelSerializer):
    areaM2 = serializers.DecimalField(
        source="area_m2", max_digits=10, decimal_places=2
    )
    zoneCount = serializers.SerializerMethodField()

    class Meta:
        model = Greenhouse
        fields = (
            "id",
            "name",
            "location",
            "areaM2",
            "notes",
            "zoneCount",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "zoneCount", "created_at", "updated_at")

    def get_zoneCount(self, obj):
        if hasattr(obj, "zone_count"):
            return obj.zone_count
        return obj.zones.count()


class ZoneSerializer(serializers.ModelSerializer):
    greenhouseId = serializers.PrimaryKeyRelatedField(
        source="greenhouse", queryset=Greenhouse.objects.all()
    )
    zoneCode = serializers.CharField(source="zone_code")
    cropName = serializers.CharField(source="crop_name", allow_blank=True, required=False)
    greenhouseName = serializers.CharField(source="greenhouse.name", read_only=True)

    class Meta:
        model = Zone
        fields = (
            "id",
            "greenhouseId",
            "greenhouseName",
            "zoneCode",
            "cropName",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "greenhouseName", "created_at", "updated_at")

    def validate(self, attrs):
        greenhouse = attrs.get("greenhouse") or getattr(self.instance, "greenhouse", None)
        zone_code = attrs.get("zone_code") or getattr(self.instance, "zone_code", None)
        if greenhouse and zone_code:
            qs = Zone.objects.filter(greenhouse=greenhouse, zone_code=zone_code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"zoneCode": "同一温室内分区编码必须唯一"}
                )
        return attrs


class ClimateLogSerializer(serializers.ModelSerializer):
    zoneId = serializers.PrimaryKeyRelatedField(
        source="zone", queryset=Zone.objects.all()
    )
    recordedAt = serializers.DateTimeField(source="recorded_at")
    tempC = serializers.DecimalField(source="temp_c", max_digits=5, decimal_places=2)
    humidityPct = serializers.DecimalField(
        source="humidity_pct", max_digits=5, decimal_places=2
    )
    parUmol = serializers.DecimalField(
        source="par_umol", max_digits=8, decimal_places=2, required=False
    )
    co2Ppm = serializers.DecimalField(
        source="co2_ppm", max_digits=8, decimal_places=2, required=False
    )
    zoneCode = serializers.CharField(source="zone.zone_code", read_only=True)
    greenhouseName = serializers.CharField(
        source="zone.greenhouse.name", read_only=True
    )

    class Meta:
        model = ClimateLog
        fields = (
            "id",
            "zoneId",
            "zoneCode",
            "greenhouseName",
            "recordedAt",
            "tempC",
            "humidityPct",
            "parUmol",
            "co2Ppm",
            "created_at",
        )
        read_only_fields = ("id", "zoneCode", "greenhouseName", "created_at")

    def validate_humidityPct(self, value):
        if value < 20 or value > 100:
            raise serializers.ValidationError("湿度须在 20～100 之间")
        return value


class IrrigationDurationRevisionSerializer(serializers.ModelSerializer):
    cycleId = serializers.IntegerField(source="cycle_id", read_only=True)
    oldMin = serializers.IntegerField(source="old_min", read_only=True)
    newMin = serializers.IntegerField(source="new_min", read_only=True)
    revisedAt = serializers.DateTimeField(source="revised_at", read_only=True)

    class Meta:
        model = IrrigationDurationRevision
        fields = ("id", "cycleId", "oldMin", "newMin", "reason", "revisedAt")
        read_only_fields = fields


class IrrigationCycleSerializer(serializers.ModelSerializer):
    zoneId = serializers.PrimaryKeyRelatedField(
        source="zone", queryset=Zone.objects.all()
    )
    startAt = serializers.DateTimeField(source="start_at")
    durationMin = serializers.IntegerField(source="duration_min", min_value=1)
    waterLiters = serializers.DecimalField(
        source="water_liters", max_digits=10, decimal_places=2
    )
    zoneCode = serializers.CharField(source="zone.zone_code", read_only=True)
    greenhouseName = serializers.CharField(
        source="zone.greenhouse.name", read_only=True
    )
    revisionCount = serializers.SerializerMethodField()
    latestDurationMin = serializers.SerializerMethodField()
    revisionReason = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=500
    )

    class Meta:
        model = IrrigationCycle
        fields = (
            "id",
            "zoneId",
            "zoneCode",
            "greenhouseName",
            "startAt",
            "durationMin",
            "latestDurationMin",
            "revisionCount",
            "revisionReason",
            "waterLiters",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "zoneCode",
            "greenhouseName",
            "latestDurationMin",
            "revisionCount",
            "created_at",
            "updated_at",
        )

    def get_revisionCount(self, obj):
        if hasattr(obj, "revision_count"):
            return obj.revision_count
        return obj.duration_revisions.count()

    def get_latestDurationMin(self, obj):
        # 最新时长 = 最新留痕的新分钟；无留痕则等于当前时长
        latest = obj.duration_revisions.all().first()
        if latest is None:
            return obj.duration_min
        return latest.new_min

    def validate(self, attrs):
        # 改时长且新值与库中不同：必须给出有效修订原因，否则 400 且时长保持原值
        if self.instance is not None and "duration_min" in attrs:
            new_min = attrs["duration_min"]
            if new_min != self.instance.duration_min:
                reason = (attrs.get("revisionReason") or "").strip()
                if len(reason) < IrrigationDurationRevision.REASON_MIN_LEN:
                    raise serializers.ValidationError(
                        {
                            "revisionReason": "修改时长必须填写修订原因（去空白后至少 8 字），缺留痕则时长保持原值"
                        }
                    )
                attrs["revisionReason"] = reason
        return attrs

    def create(self, validated_data):
        validated_data.pop("revisionReason", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        reason = validated_data.pop("revisionReason", None)
        new_min = validated_data.get("duration_min")
        with transaction.atomic():
            if reason and new_min is not None and new_min != instance.duration_min:
                # 同事务先写留痕，再更新时长；任一步失败整体回滚
                IrrigationDurationRevision.objects.create(
                    cycle=instance,
                    old_min=instance.duration_min,
                    new_min=new_min,
                    reason=reason,
                )
            return super().update(instance, validated_data)
