"""Viste della sezione Configurazione (accessibile solo a staff).

CRUD per TipoAdempimentoCatalogo con gestione inline di scadenze,
checklist e regole di applicabilità. La pagina di dettaglio espone i tre
gruppi come tab distinti per non affollare un unico form.
"""
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    ChecklistStepForm,
    RegolaApplicabilitaForm,
    ScadenzaPeriodoForm,
    TipoAdempimentoCatalogoForm,
)
from .models import (
    ChecklistStep,
    RegolaApplicabilita,
    ScadenzaPeriodo,
    TipoAdempimentoCatalogo,
)


TAB_GENERALE = "generale"
TAB_SCADENZE = "scadenze"
TAB_CHECKLIST = "checklist"
TAB_REGOLE = "regole"
TABS_VALIDI = {TAB_GENERALE, TAB_SCADENZE, TAB_CHECKLIST, TAB_REGOLE}


def _redirect_tab(pk: int, tab: str):
    return redirect(reverse("configurazione:tipo_detail", args=[pk]) + f"?tab={tab}")


def _prossimo_ordine(qs, step: int = 10) -> int:
    last = qs.order_by("-ordine").first()
    return (last.ordine + step) if last else step


# ---------------------------------------------------------------------------
# Tipi adempimento
# ---------------------------------------------------------------------------

@staff_member_required
def configurazione_home(request):
    return redirect("configurazione:tipi_list")


@staff_member_required
def tipi_list(request):
    tipi = TipoAdempimentoCatalogo.objects.all().order_by("ordine", "denominazione")
    return render(
        request,
        "configurazione/tipi_list.html",
        {"tipi": tipi, "totale": tipi.count()},
    )


@staff_member_required
def tipo_create(request):
    if request.method == "POST":
        form = TipoAdempimentoCatalogoForm(request.POST)
        if form.is_valid():
            tipo = form.save()
            messages.success(request, f"Tipo '{tipo.denominazione}' creato.")
            return redirect("configurazione:tipo_detail", pk=tipo.pk)
    else:
        form = TipoAdempimentoCatalogoForm()
    return render(
        request,
        "configurazione/tipo_form.html",
        {"form": form, "modalita": "crea"},
    )


@staff_member_required
def tipo_detail(request, pk: int):
    tipo = get_object_or_404(TipoAdempimentoCatalogo, pk=pk)
    tab = request.GET.get("tab", TAB_GENERALE)
    if tab not in TABS_VALIDI:
        tab = TAB_GENERALE

    context = {"tipo": tipo, "tab": tab}

    if tab == TAB_GENERALE:
        context["form"] = TipoAdempimentoCatalogoForm(instance=tipo)
    elif tab == TAB_SCADENZE:
        context["scadenze"] = tipo.scadenze.all().order_by("periodo")
        context["nuova_scadenza_form"] = ScadenzaPeriodoForm()
    elif tab == TAB_CHECKLIST:
        context["steps"] = tipo.checklist_steps.all().order_by("ordine")
        context["nuovo_step_form"] = ChecklistStepForm(
            initial={"ordine": _prossimo_ordine(tipo.checklist_steps.all())}
        )
    elif tab == TAB_REGOLE:
        context["regole"] = tipo.regole.all().order_by("ordine")
        context["nuova_regola_form"] = RegolaApplicabilitaForm(
            initial={"ordine": _prossimo_ordine(tipo.regole.all())}
        )

    return render(request, "configurazione/tipo_detail.html", context)


@staff_member_required
@require_POST
def tipo_edit(request, pk: int):
    tipo = get_object_or_404(TipoAdempimentoCatalogo, pk=pk)
    form = TipoAdempimentoCatalogoForm(request.POST, instance=tipo)
    if form.is_valid():
        form.save()
        messages.success(request, "Tipo aggiornato.")
        return _redirect_tab(pk, TAB_GENERALE)
    return render(
        request,
        "configurazione/tipo_detail.html",
        {"tipo": tipo, "tab": TAB_GENERALE, "form": form},
    )


@staff_member_required
@require_POST
def tipo_delete(request, pk: int):
    tipo = get_object_or_404(TipoAdempimentoCatalogo, pk=pk)
    if tipo.adempimenti.exists():
        messages.error(
            request,
            "Impossibile eliminare: esistono adempimenti operativi di questo tipo. "
            "Disattivalo invece di cancellarlo.",
        )
        return redirect("configurazione:tipo_detail", pk=pk)
    nome = tipo.denominazione
    tipo.delete()
    messages.success(request, f"Tipo '{nome}' eliminato.")
    return redirect("configurazione:tipi_list")


# ---------------------------------------------------------------------------
# Scadenze
# ---------------------------------------------------------------------------

@staff_member_required
@require_POST
def scadenza_create(request, pk: int):
    tipo = get_object_or_404(TipoAdempimentoCatalogo, pk=pk)
    form = ScadenzaPeriodoForm(request.POST)
    if form.is_valid():
        scadenza = form.save(commit=False)
        scadenza.tipo_adempimento = tipo
        try:
            scadenza.save()
        except IntegrityError:
            messages.error(
                request,
                f"Esiste già una scadenza per il periodo {scadenza.periodo} "
                f"su questo tipo. Modifica l'esistente o scegli un altro periodo.",
            )
        else:
            messages.success(request, "Scadenza aggiunta.")
    else:
        _flash_form_errors(request, form)
    return _redirect_tab(pk, TAB_SCADENZE)


@staff_member_required
@require_POST
def scadenza_delete(request, pk: int, sid: int):
    get_object_or_404(
        ScadenzaPeriodo, pk=sid, tipo_adempimento_id=pk
    ).delete()
    messages.success(request, "Scadenza rimossa.")
    return _redirect_tab(pk, TAB_SCADENZE)


# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------

@staff_member_required
@require_POST
def step_create(request, pk: int):
    tipo = get_object_or_404(TipoAdempimentoCatalogo, pk=pk)
    form = ChecklistStepForm(request.POST)
    if form.is_valid():
        step = form.save(commit=False)
        step.tipo_adempimento = tipo
        step.save()
        messages.success(request, "Step aggiunto.")
    else:
        _flash_form_errors(request, form)
    return _redirect_tab(pk, TAB_CHECKLIST)


@staff_member_required
@require_POST
def step_delete(request, pk: int, sid: int):
    get_object_or_404(
        ChecklistStep, pk=sid, tipo_adempimento_id=pk
    ).delete()
    messages.success(request, "Step rimosso.")
    return _redirect_tab(pk, TAB_CHECKLIST)


# ---------------------------------------------------------------------------
# Regole
# ---------------------------------------------------------------------------

@staff_member_required
@require_POST
def regola_create(request, pk: int):
    tipo = get_object_or_404(TipoAdempimentoCatalogo, pk=pk)
    form = RegolaApplicabilitaForm(request.POST)
    if form.is_valid():
        regola = form.save(commit=False)
        regola.tipo_adempimento = tipo
        regola.save()
        messages.success(request, "Regola aggiunta.")
    else:
        _flash_form_errors(request, form)
    return _redirect_tab(pk, TAB_REGOLE)


@staff_member_required
@require_POST
def regola_delete(request, pk: int, rid: int):
    get_object_or_404(
        RegolaApplicabilita, pk=rid, tipo_adempimento_id=pk
    ).delete()
    messages.success(request, "Regola rimossa.")
    return _redirect_tab(pk, TAB_REGOLE)


# ---------------------------------------------------------------------------

def _flash_form_errors(request, form):
    for field, errors in form.errors.items():
        label = form.fields.get(field).label if field in form.fields else field
        for err in errors:
            messages.error(request, f"{label}: {err}")
