from django.contrib import admin
from django.urls import path, include
from core.views import dashboard_redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('operations.urls')),
    path('', include('core.urls')),
    path('auth/', include('core.urls')),
]
