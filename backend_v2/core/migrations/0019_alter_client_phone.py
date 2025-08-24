from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_handle_duplicate_phones'),
    ]

    operations = [
        migrations.AlterField(
            model_name='client',
            name='phone',
            field=models.CharField(blank=True, max_length=20, null=True, unique=True),
        ),
    ]
