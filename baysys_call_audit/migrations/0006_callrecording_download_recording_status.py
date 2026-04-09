from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Adds download_recording_status to Django's migration state.

    PRODUCTION DEPLOY: column already exists in uvarcl_live.call_recordings
    (created by CRM download job). Run with --fake so no DDL is executed:

        python manage.py migrate baysys_call_audit 0006 --fake

    Test runner uses a fresh SQLite DB, so the AddField runs normally there.
    """

    dependencies = [
        ("baysys_call_audit", "0005_provider_score_audit_params_transcript_prompt"),
    ]

    operations = [
        migrations.AddField(
            model_name="callrecording",
            name="download_recording_status",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
