from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404, render

from anagrafica.models import AnagraficaReferenteStudio, RuoloReferenteStudio

from .models import Adempimento, StatoAdempimento, TipoAdempimentoCatalogo


@login_required
def lista_adempimenti(request):
    qs = Adempimento.objects.filter(is_deleted=False).select_related(
        "anagrafica", "responsabile", "tipo"
    )

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(anagrafica__denominazione__icontains=q)
            | Q(anagrafica__codice_interno__icontains=q)
        )

    tipo_id = request.GET.get("tipo", "")
    if tipo_id.isdigit():
        qs = qs.filter(tipo_id=int(tipo_id))

    anno_fiscale = request.GET.get("anno_fiscale", "")
    if anno_fiscale.isdigit():
        qs = qs.filter(anno_fiscale=int(anno_fiscale))

    stato = request.GET.get("stato", "")
    if stato in StatoAdempimento.values:
        qs = qs.filter(stato=stato)

    esecutore = request.GET.get("esecutore", "")
    if esecutore.isdigit():
        qs = qs.filter(responsabile_id=int(esecutore))

    referente_ruolo = request.GET.get("ref_ruolo", "")
    referente_utente = request.GET.get("ref_utente", "")
    if (
        referente_ruolo in RuoloReferenteStudio.values
        and referente_utente.isdigit()
    ):
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

    qs = qs.order_by("data_scadenza", "anagrafica__denominazione")

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page": page,
        "adempimenti": page.object_list,
        "q": q,
        "tipo_id": tipo_id,
        "anno_fiscale": anno_fiscale,
        "stato": stato,
        "esecutore": esecutore,
        "tipi": TipoAdempimentoCatalogo.objects.filter(attivo=True),
        "stati": StatoAdempimento.choices,
        "ruoli": RuoloReferenteStudio.choices,
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
        Adempimento.objects.select_related("anagrafica", "responsabile", "tipo"),
        pk=pk,
        is_deleted=False,
    )
    steps = adempimento.steps_completati.select_related("step", "completato_da").order_by("step__ordine")
    return render(
        request,
        "adempimenti/detail.html",
        {
            "adempimento": adempimento,
            "steps": steps,
            "addetti": adempimento.addetti_contabilita_cliente,
            "consulenti": adempimento.responsabili_consulenza_cliente,
        },
    )
