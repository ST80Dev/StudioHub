from django.urls import path

from . import views

app_name = "adempimenti"

urlpatterns = [
    path("", views.lista_adempimenti, name="list"),
    # Vista dedicata Liquidazione IVA Trimestrale (LIPE)
    path("liquidazione-iva-trimestrale/", views.lista_lipe, name="lipe"),
    path(
        "liquidazione-iva-trimestrale/aggiungi-cliente/",
        views.lipe_aggiungi_cliente,
        name="lipe_aggiungi_cliente",
    ),
    path(
        "liquidazione-iva-trimestrale/sincronizza/",
        views.lipe_sincronizza,
        name="lipe_sincronizza",
    ),
    path(
        "liquidazione-iva-trimestrale/<int:pk>/rimuovi/",
        views.lipe_rimuovi_riga,
        name="lipe_rimuovi_riga",
    ),
    path(
        "liquidazione-iva-trimestrale/cerca-clienti/",
        views.lipe_search_clienti,
        name="lipe_search_clienti",
    ),
    path(
        "liquidazione-iva-trimestrale/bulk/",
        views.lipe_bulk_update,
        name="lipe_bulk_update",
    ),
    path(
        "liquidazione-iva-trimestrale/<int:pk>/inline/<str:field>/edit/",
        views.lipe_inline_edit_form,
        name="lipe_inline_edit_form",
    ),
    path(
        "liquidazione-iva-trimestrale/<int:pk>/inline/<str:field>/",
        views.lipe_inline_save,
        name="lipe_inline_save",
    ),
    path("<int:pk>/", views.dettaglio_adempimento, name="detail"),
]
