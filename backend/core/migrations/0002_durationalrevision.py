import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DurationRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("old_min", models.PositiveIntegerField()),
                ("new_min", models.PositiveIntegerField()),
                ("reason", models.CharField(max_length=300)),
                ("revised_at", models.DateTimeField(auto_now_add=True)),
                (
                    "cycle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="duration_revisions",
                        to="core.irrigationcycle",
                    ),
                ),
            ],
            options={
                "ordering": ["-revised_at", "-id"],
            },
        ),
    ]
