from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("audit/", include("baysys_call_audit.urls")),
]
