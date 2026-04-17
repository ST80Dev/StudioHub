from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from adempimenti.models import Adempimento, StatoAdempimento
from anagrafica.models import Anagrafica


@login_required
def home(request):
    user = request.user

    clienti_attivi = Anagrafica.objects.filter(
        is_deleted=False, stato="attivo"
    ).count()

    miei_adempimenti = (
        Adempimento.objects.filter(is_deleted=False, responsabile=user)
        .exclude(stato=StatoAdempimento.INVIATO)
        .select_related("anagrafica", "tipo")
        .order_by("data_scadenza")[:20]
    )

    context = {
        "clienti_attivi": clienti_attivi,
        "miei_adempimenti": miei_adempimenti,
        "totale_adempimenti": Adempimento.objects.filter(is_deleted=False).count(),
    }
    return render(request, "core/home.html", context)
