from django.contrib import admin
from django.urls import path, include
from dashboard import views, api_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.dashboard, name='dashboard'),
    path('scrapers/', views.scrapers_list, name='scrapers_list'),
    path('scrapers/<int:pk>/', views.main_scraper_detail, name='main_scraper_detail'),
    path('scrapers/new/', views.main_scraper_create, name='main_scraper_create'),
    path('scrapers/<int:pk>/edit/', views.main_scraper_edit, name='main_scraper_edit'),
    path('scrapers/<int:pk>/sub/new/', views.sub_scraper_create, name='sub_scraper_create'),
    path('scrapers/<int:pk>/sub/<int:sub_id>/', views.sub_scraper_detail, name='sub_scraper_detail'),
    path('scrapers/<int:pk>/sub/<int:sub_id>/edit/', views.sub_scraper_edit, name='sub_scraper_edit'),
    path('scrapers/<int:pk>/sub/<int:sub_id>/logs/', views.log_viewer, name='log_viewer'),
    path('scrapers/<int:pk>/sub/<int:sub_id>/terminal/', views.live_terminal, name='live_terminal'),
    path('scrapers/<int:pk>/sub/<int:sub_id>/schedule/', views.schedule_management, name='schedule_management'),
    path('scrapers/<int:pk>/sub/<int:sub_id>/history/', views.run_history, name='run_history'),
    path('scrapers/<int:pk>/sub/<int:sub_id>/mongo/', views.mongo_panel, name='mongo_panel'),
    path('scrapers/<int:pk>/sub/<int:sub_id>/run/', views.run_scraper, name='run_scraper'),
    path('scrapers/<int:pk>/sub/<int:sub_id>/stop/', views.stop_scraper, name='stop_scraper'),
    path('watcher/', views.watcher, name='watcher'),

    # Existing API endpoints
    path('api/logs/', api_views.api_log_tail, name='api_log_tail'),
    path('api/status/<int:sub_id>/', api_views.api_status, name='api_status'),
    path('api/watcher-data/', api_views.api_watcher_data, name='api_watcher_data'),

    # Live terminal API endpoints
    path('api/live-log/<int:sub_id>/', api_views.api_live_log, name='api_live_log'),
    path('api/send-input/<int:sub_id>/', api_views.api_send_input, name='api_send_input'),
]
