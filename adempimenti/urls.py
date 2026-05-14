from django.urls import path

from . import views

app_name = "adempimenti"

urlpatterns = [
    path("", views.lista_adempimenti, name="list"),

    # Vista dedicata per un tipo di adempimento del catalogo.
    # L'URL identifica il tipo per PK (non per codice) così il `codice` del
    # catalogo resta liberamente modificabile dall'utente senza rompere
    # URL, bookmark e reverse interne.
    path(
        "tipo/<int:catalogo_id>/",
        views.lista_tipo,
        name="lista_tipo",
    ),
    path(
        "tipo/<int:catalogo_id>/aggiungi-cliente/",
        views.tipo_aggiungi_cliente,
        name="tipo_aggiungi_cliente",
    ),
    path(
        "tipo/<int:catalogo_id>/sincronizza/",
        views.tipo_sincronizza,
        name="tipo_sincronizza",
    ),
    path(
        "tipo/<int:catalogo_id>/cerca-clienti/",
        views.tipo_search_clienti,
        name="tipo_search_clienti",
    ),
    path(
        "tipo/<int:catalogo_id>/bulk/",
        views.tipo_bulk_update,
        name="tipo_bulk_update",
    ),
    path(
        "tipo/<int:catalogo_id>/riga/<int:pk>/rimuovi/",
        views.tipo_rimuovi_riga,
        name="tipo_rimuovi_riga",
    ),
    path(
        "tipo/<int:catalogo_id>/riga/<int:pk>/inline/<str:field>/edit/",
        views.tipo_inline_edit_form,
        name="tipo_inline_edit_form",
    ),
    path(
        "tipo/<int:catalogo_id>/riga/<int:pk>/inline/<str:field>/",
        views.tipo_inline_save,
        name="tipo_inline_save",
    ),

    # Redirect legacy: i vecchi URL `/adempimenti/liquidazione-iva-trimestrale/`
    # restano funzionanti per bookmark e link salvati; rispondono 301 al nuovo
    # URL basato su PK.
    path(
        "liquidazione-iva-trimestrale/",
        views.legacy_lipe_redirect,
    ),

    path("<int:pk>/", views.dettaglio_adempimento, name="detail"),
]
