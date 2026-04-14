from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from anagrafica.models import RuoloReferenteStudio

from .models import Adempimento, StatoBilancioUE, TipoAdempimento


@login_required
def lista_adempimenti(request):
    qs = Adempimento.objects.filter(is_deleted=False).select_related(
        "anagrafica", "responsabile"
    )

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(anagrafica__denominazione__icontains=q)
            | Q(anagrafica__codice_interno__icontains=q)
        )

    tipo = request.GET.get("tipo", "")
    if tipo in TipoAdempimento.values:
        qs = qs.filter(tipo=tipo)

    anno_fiscale = request.GET.get("anno_fiscale", "")
    if anno_fiscale.isdigit():
        qs = qs.filter(anno_fiscale=int(anno_fiscale))

    anno_esecuzione = request.GET.get("anno_esecuzione", "")
    if anno_esecuzione.isdigit():
        qs = qs.filter(anno_esecuzione=int(anno_esecuzione))

    esecutore = request.GET.get("esecutore", "")
    if esecutore.isdigit():
        qs = qs.filter(responsabile_id=int(esecutore))

    # Filtro per responsabile consulenza / addetto contabilità del cliente
    # (opzione B: validi nell'anno fiscale dell'adempimento)
    referente_ruolo = request.GET.get("ref_ruolo", "")
    referente_utente = request.GET.get("ref_utente", "")
    if (
        referente_ruolo in RuoloReferenteStudio.values
        and referente_utente.isdigit()
    ):
        # Correlated subquery a livello applicativo
        from anagrafica.models import AnagraficaReferenteStudio
        from django.db.models import Exists, OuterRef
        from datetime import date

        sub = AnagraficaReferenteStudio.objects.filter(
            anagrafica=OuterRef("anagrafica"),
            utente_id=int(referente_utente),
            ruolo=referente_ruolo,
            data_inizio__year__lte=OuterRef("anno_fiscale"),
        ).filter(
            Q(data_fine__isnull=True)
            | Q(data_fine__year__gte=OuterRef("anno_fiscale"))
        )
        qs = qs.filter(Exists(sub))

    qs = qs.order_by("-anno_esecuzione", "anagrafica__denominazione")

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page": page,
        "adempimenti": page.object_list,
        "q": q,
        "tipo": tipo,
        "anno_fiscale": anno_fiscale,
        "anno_esecuzione": anno_esecuzione,
        "esecutore": esecutore,
        "tipi": TipoAdempimento.choices,
        "ruoli": RuoloReferenteStudio.choices,
        "stati_bilancio_ue": StatoBilancioUE.choices,
        "totale": paginator.count,
    }
    template = (
        "adempimenti/_list_rows.html"
        if request.htmx
        else "adempimenti/list.html"
    )
    return render(request, template, context)


@login_required
def dettaglio_adempimento(request, pk: int):
    adempimento = get_object_or_404(
        Adempimento.objects.select_related("anagrafica", "responsabile"),
        pk=pk,
        is_deleted=False,
    )
    return render(
        request,
        "adempimenti/detail.html",
        {
            "adempimento": adempimento,
            "dettaglio": adempimento.dettaglio,
            "addetti": adempimento.addetti_contabilita_cliente,
            "consulenti": adempimento.responsabili_consulenza_cliente,
        },
    )
