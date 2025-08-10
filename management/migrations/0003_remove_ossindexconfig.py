from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('management', '0002_ossindexconfig_email_alter_ossindexconfig_api_token'),
    ]

    operations = [
        # Remove the OSSIndexConfig model and its table
        migrations.DeleteModel(
            name='OSSIndexConfig',
        ),
        # Safety: ensure table is dropped if it still exists
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS management_ossindexconfig CASCADE;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]


