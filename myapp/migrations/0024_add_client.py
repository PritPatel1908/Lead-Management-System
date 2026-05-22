"""Add Client model."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('myapp', '0023_add_lead_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='Client',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('address', models.TextField(blank=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('number', models.CharField(max_length=50, blank=True)),
                ('is_draft', models.BooleanField(default=False)),
                ('is_delete', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'Client',
                'verbose_name_plural': 'Clients',
                'db_table': 'client',
            },
        ),
    ]
