from django.urls import path

from . import views

app_name = "importazione"

urlpatterns = [
    path("", views.session_list, name="list"),
    path("nuova/", views.session_create, name="create"),
    path("<int:pk>/", views.session_detail, name="detail"),
    path("<int:pk>/mapping/", views.session_mapping_edit, name="mapping_edit"),
    path("<int:pk>/match/", views.session_run_matching, name="run_matching"),
    path("<int:pk>/decisione-bulk/", views.session_bulk_decisione, name="bulk_decisione"),
    path("<int:pk>/applica/", views.session_apply_preview, name="apply_preview"),
    path("<int:pk>/applica/esegui/", views.session_apply_run, name="apply_run"),
    path("<int:pk>/elimina/", views.session_delete, name="delete"),
    path("riga/<int:pk>/", views.row_update, name="row_update"),
    path("anagrafica/search/", views.anagrafica_search, name="anagrafica_search"),
]
