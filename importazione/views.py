from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import ImportSession


@login_required
def session_list(request):
    """Elenco sessioni di import. UI di upload/mapping/preview verrà aggiunta nei prossimi step."""
    sessioni = ImportSession.objects.select_related("creato_da").order_by("-created_at")
    return render(
        request,
        "importazione/session_list.html",
        {"sessioni": sessioni},
    )
