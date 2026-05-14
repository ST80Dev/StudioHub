from django.urls import path

from . import views

app_name = "anagrafica"

urlpatterns = [
    path("", views.lista_clienti, name="list"),
    path("diagnostica/", views.diagnostica, name="diagnostica"),
    path("diagnostica/remap/", views.diagnostica_remap, name="diagnostica_remap"),
    path("modifica-bulk/", views.bulk_update, name="bulk_update"),
    path("<int:pk>/", views.dettaglio_cliente, name="detail"),
    path("<int:pk>/modifica/", views.modifica_cliente, name="edit"),
    path("<int:pk>/inline/<str:field>/edit/", views.inline_edit_form, name="inline_edit_form"),
    path("<int:pk>/inline/<str:field>/", views.inline_save, name="inline_save"),
    # Inline edit referenti (storicizzato con conferma data)
    path("<int:pk>/referente/<str:ruolo>/", views.referente_cell, name="referente_cell"),
    path("<int:pk>/referente/<str:ruolo>/edit/", views.referente_edit_form, name="referente_edit_form"),
    path("<int:pk>/referente/<str:ruolo>/save/", views.referente_save, name="referente_save"),
    # Categorie (tag) sull'anagrafica
    path("<int:pk>/categorie/cerca/", views.categorie_search, name="categorie_search"),
    path("<int:pk>/categorie/assegna/", views.categorie_assegna, name="categorie_assegna"),
    path("<int:pk>/categorie/<int:cat_pk>/rimuovi/", views.categorie_rimuovi, name="categorie_rimuovi"),
]
