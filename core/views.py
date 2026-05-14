from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef
from django.shortcuts import render

from adempimenti.models import Adempimento, StatoAdempimentoTipo
from anagrafica.models import Anagrafica


@login_required
def home(request):
    user = request.user

    clienti_attivi = Anagrafica.objects.filter(
        is_deleted=False, stato="attivo"
    ).count()

    # "Miei adempimenti residui" = adempimenti assegnati a me, in uno stato
    # ancora lavorabile. Il flag `lavorabile` vive sul catalogo stati DEL
    # TIPO (cosi' un nuovo stato terminale aggiunto da admin viene escluso
    # automaticamente senza modifiche al codice).
    lavorabile_subq = StatoAdempimentoTipo.objects.filter(
        tipo_adempimento=OuterRef("tipo"),
        codice=OuterRef("stato"),
        lavorabile=True,
        attivo=True,
    )
    miei_adempimenti = (
        Adempimento.objects.filter(is_deleted=False, responsabile=user)
        .filter(Exists(lavorabile_subq))
        .select_related("anagrafica", "tipo")
        .order_by("data_scadenza")[:20]
    )

    context = {
        "clienti_attivi": clienti_attivi,
        "miei_adempimenti": miei_adempimenti,
        "totale_adempimenti": Adempimento.objects.filter(is_deleted=False).count(),
    }
    return render(request, "core/home.html", context)
