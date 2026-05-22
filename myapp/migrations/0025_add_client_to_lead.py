"""Add `client` FK to Lead."""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0024_add_client'),
    ]

    operations = [
        migrations.AddField(
            model_name='lead',
            name='client',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='leads', to='myapp.client'),
        ),
    ]
