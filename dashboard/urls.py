from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="fetch_home"),
    path("fetch/", views.fetch_video, name="fetch_video"),
    path("dashboard/", views.overview, name="dashboard"),
    path("overview/", views.overview, name="overview"),
    path(
        "analysis/<str:video_id>/",
        views.analysis,
        name="analysis",
    ),
    path(
        "comparison/",
        views.comparison,
        name="comparison",
    ),

]