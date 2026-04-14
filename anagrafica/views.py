from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import Anagrafica, StatoAnagrafica, TipoSoggetto


@login_required
def lista_clienti(request):
    """Lista densa dei clienti, con ricerca libera e filtri rapidi."""
    queryset = Anagrafica.objects.filter(is_deleted=False)

    q = request.GET.get("q", "").strip()
    if q:
        queryset = queryset.filter(
            Q(denominazione__icontains=q)
            | Q(codice_interno__icontains=q)
            | Q(codice_fiscale__icontains=q)
            | Q(partita_iva__icontains=q)
        )

    tipo = request.GET.get("tipo", "")
    if tipo in TipoSoggetto.values:
        queryset = queryset.filter(tipo_soggetto=tipo)

    stato = request.GET.get("stato", "")
    if stato in StatoAnagrafica.values:
        queryset = queryset.filter(stato=stato)

    paginator = Paginator(queryset.order_by("denominazione"), 50)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page": page,
        "clienti": page.object_list,
        "q": q,
        "tipo": tipo,
        "stato": stato,
        "tipi_soggetto": TipoSoggetto.choices,
        "stati": StatoAnagrafica.choices,
        "totale": paginator.count,
    }
    template = (
        "anagrafica/_list_rows.html" if request.htmx else "anagrafica/list.html"
    )
    return render(request, template, context)


@login_required
def dettaglio_cliente(request, pk: int):
    cliente = get_object_or_404(Anagrafica, pk=pk, is_deleted=False)
    return render(
        request,
        "anagrafica/detail.html",
        {
            "cliente": cliente,
            "referenti_attivi": cliente.referenti_studio.filter(
                data_fine__isnull=True
            ).select_related("utente"),
            "legami": cliente.legami_da.select_related("anagrafica_collegata"),
        },
    )
