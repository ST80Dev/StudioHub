from django.urls import path

from . import views

app_name = "importazione"

urlpatterns = [
    path("", views.session_list, name="list"),
    path("nuova/", views.session_create, name="create"),
    path("<int:pk>/", views.session_detail, name="detail"),
    path("<int:pk>/elimina/", views.session_delete, name="delete"),
]
