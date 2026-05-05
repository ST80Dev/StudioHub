from django.urls import path

from . import views

app_name = "importazione"

urlpatterns = [
    path("", views.session_list, name="list"),
]
