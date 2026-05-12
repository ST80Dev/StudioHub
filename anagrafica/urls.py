from django.urls import path

from . import views

app_name = "anagrafica"

urlpatterns = [
    path("", views.lista_clienti, name="list"),
    path("modifica-bulk/", views.bulk_update, name="bulk_update"),
    path("<int:pk>/", views.dettaglio_cliente, name="detail"),
    path("<int:pk>/modifica/", views.modifica_cliente, name="edit"),
]
