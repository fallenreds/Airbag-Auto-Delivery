from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_remove_client_discount_percent"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="remonline_sync_status",
            field=models.CharField(
                choices=[("PENDING", "Pending"), ("SYNCED", "Synced")],
                default="PENDING",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="orderevent",
            name="type",
            field=models.CharField(
                choices=[
                    ("MERGED", "Merged"),
                    ("CREATED_ADMIN_MESSAGE", "Created Admin Message"),
                    ("CREATED_CLIENT_MESSAGE", "Created Client Message"),
                    ("FINISHED", "Finished"),
                    ("TTN_UPDATED", "TTN Updated"),
                    ("IN_BRANCH", "In Branch"),
                    ("PAYMENT_CONFIRMED", "Payment Confirmed"),
                    ("REMONLINE_CREATED", "Remonline Created"),
                    ("PAYMENT_TYPE_CHANGED", "Payment Type Changed"),
                ],
                max_length=32,
            ),
        ),
    ]

