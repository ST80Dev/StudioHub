from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render

from adempimenti.models import Adempimento
from anagrafica.models import Anagrafica


@login_required
def home(request):
    """Dashboard personale: qualche contatore per orientarsi al volo."""
    user = request.user

    clienti_attivi = Anagrafica.objects.filter(
        is_deleted=False, stato="attivo"
    ).count()

    miei_adempimenti = Adempimento.objects.filter(
        is_deleted=False, responsabile=user
    ).select_related("anagrafica").order_by("-anno_esecuzione")[:20]

    context = {
        "clienti_attivi": clienti_attivi,
        "miei_adempimenti": miei_adempimenti,
        "totale_adempimenti": Adempimento.objects.filter(is_deleted=False).count(),
    }
    return render(request, "core/home.html", context)
