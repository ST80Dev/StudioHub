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
    # Categorie (tag) sull'anagrafica
    path("<int:pk>/categorie/cerca/", views.categorie_search, name="categorie_search"),
    path("<int:pk>/categorie/assegna/", views.categorie_assegna, name="categorie_assegna"),
    path("<int:pk>/categorie/<int:cat_pk>/rimuovi/", views.categorie_rimuovi, name="categorie_rimuovi"),
    # Referenti studio sull'anagrafica
    path("<int:pk>/referenti/aggiungi/", views.referente_aggiungi, name="referente_aggiungi"),
    path("<int:pk>/referenti/<int:rid>/chiudi/", views.referente_chiudi, name="referente_chiudi"),
    path("<int:pk>/referenti/<int:rid>/principale/", views.referente_principale, name="referente_principale"),
]
