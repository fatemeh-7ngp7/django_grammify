# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse


def health(request):
    return JsonResponse({"status": "ok", "service": "Grammify"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/auth/", include("apps.accounts.urls", namespace="accounts")),
    #path("api/", include("apps.processing.urls", namespace="processing")),
]
