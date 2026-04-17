from django.urls import path

from . import config_views as v

app_name = "configurazione"

urlpatterns = [
    path("", v.configurazione_home, name="home"),
    path("matrice/", v.matrice, name="matrice"),
    path("tipi/", v.tipi_list, name="tipi_list"),
    path("tipi/nuovo/", v.tipo_create, name="tipo_create"),
    path("tipi/<int:pk>/", v.tipo_detail, name="tipo_detail"),
    path("tipi/<int:pk>/modifica/", v.tipo_edit, name="tipo_edit"),
    path("tipi/<int:pk>/elimina/", v.tipo_delete, name="tipo_delete"),
    # Scadenze
    path(
        "tipi/<int:pk>/scadenze/nuova/",
        v.scadenza_create,
        name="scadenza_create",
    ),
    path(
        "tipi/<int:pk>/scadenze/<int:sid>/elimina/",
        v.scadenza_delete,
        name="scadenza_delete",
    ),
    # Checklist
    path(
        "tipi/<int:pk>/checklist/nuovo/",
        v.step_create,
        name="step_create",
    ),
    path(
        "tipi/<int:pk>/checklist/<int:sid>/elimina/",
        v.step_delete,
        name="step_delete",
    ),
    # Regole
    path(
        "tipi/<int:pk>/regole/nuova/",
        v.regola_create,
        name="regola_create",
    ),
    path(
        "tipi/<int:pk>/regole/<int:rid>/elimina/",
        v.regola_delete,
        name="regola_delete",
    ),
]
