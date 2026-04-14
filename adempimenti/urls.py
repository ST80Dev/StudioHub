from django.urls import path

from . import views

app_name = "adempimenti"

urlpatterns = [
    path("", views.lista_adempimenti, name="list"),
    path("<int:pk>/", views.dettaglio_adempimento, name="detail"),
]
