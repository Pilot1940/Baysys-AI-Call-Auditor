from django.conf import settings
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path(f"audit/{settings.AUDIT_URL_SECRET}/", include("baysys_call_audit.urls")),
]
