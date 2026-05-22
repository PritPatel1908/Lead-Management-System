"""Auto-generated migration to add `name` field to Lead."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0022_remove_userprofile_company_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='lead',
            name='name',
            field=models.CharField(max_length=255, null=True, blank=True),
        ),
    ]
