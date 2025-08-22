# json_generator/urls.py

from django.urls import path
from . import views

app_name = 'json_generator'

urlpatterns = [
    path('', views.start_view, name='start'),

    path('get-db-info',            views.get_db_info_view,           name='get_db_info'),
    path('select-route-type/',     views.select_route_type_view,     name='select_route_type'),
    path('select-info-type/',      views.select_info_type_view,      name='select_info_type'),
    path('select-mode/',           views.select_mode_view,           name='select_mode'),
    path('insert-info/',           views.insert_info_view,           name='insert_info'),
    path('table-algo/'    ,        views.select_table_algo_view,     name='select_table_algo'),
    path('columns-filter/',        views.select_columns_filter_view, name='select_columns_filter'),
    path('generate-json/' ,        views.generate_config_json_view,  name='generate_config_json'),
    path('process-password-hash/', views.process_password_hash_view, name='process_password_hash'),
]