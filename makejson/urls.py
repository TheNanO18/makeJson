from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('json/', include('json_generator.urls')), # 이 줄을 추가
]