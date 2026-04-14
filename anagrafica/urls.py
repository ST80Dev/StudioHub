from django.urls import path

from . import views

app_name = "anagrafica"

urlpatterns = [
    path("", views.lista_clienti, name="list"),
    path("<int:pk>/", views.dettaglio_cliente, name="detail"),
]
