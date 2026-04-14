from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("preferenze/", views.preferenze, name="preferenze"),
    path("tema/", views.cambia_tema, name="cambia_tema"),
]
