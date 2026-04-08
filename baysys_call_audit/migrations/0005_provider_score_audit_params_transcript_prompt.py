from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baysys_call_audit", "0004_recording_url_charfield"),
    ]

    operations = [
        migrations.AddField(
            model_name="providerscore",
            name="audit_template_parameters",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="providerscore",
            name="function_calling_parameters",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="calltranscript",
            name="default_prompt_response",
            field=models.TextField(blank=True, null=True),
        ),
    ]
