from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import ImportSessionUploadForm
from .models import (
    ImportRow,
    ImportRowDecisione,
    ImportSession,
    ImportSessionStato,
)
from .parsing import autodetect_mapping, parse_workbook


@login_required
def session_list(request):
    sessioni = ImportSession.objects.select_related("creato_da").order_by("-created_at")
    return render(
        request,
        "importazione/session_list.html",
        {"sessioni": sessioni},
    )


@login_required
def session_create(request):
    """Step 1: upload del file. Al submit:
    - salva ImportSession
    - parsa il file e crea le ImportRow grezze
    - autodetect del mapping colonne (suggerimento, modificabile dopo)
    - redirect alla pagina di dettaglio
    """
    if request.method == "POST":
        form = ImportSessionUploadForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                sessione: ImportSession = form.save(commit=False)
                sessione.creato_da = request.user
                sessione.stato = ImportSessionStato.BOZZA
                sessione.save()

                try:
                    result = parse_workbook(
                        sessione.file.path,
                        sheet_name=sessione.sheet_name or "",
                        header_row=sessione.header_row,
                    )
                except Exception as exc:  # noqa: BLE001 — vogliamo catturare tutto qui
                    sessione.delete()
                    messages.error(
                        request,
                        f"Impossibile leggere il file: {exc}",
                    )
                    return render(
                        request,
                        "importazione/session_form.html",
                        {"form": form},
                    )

                sessione.column_mapping = autodetect_mapping(result.columns)
                sessione.riepilogo = {
                    "sheet_name": result.sheet_name,
                    "columns_detected": result.columns,
                    "sections_seen": result.sections_seen,
                    "rows_parsed": len(result.rows),
                }
                sessione.save(update_fields=["column_mapping", "riepilogo"])

                ImportRow.objects.bulk_create([
                    ImportRow(
                        sessione=sessione,
                        numero_riga=r.numero_riga,
                        dati_grezzi=r.dati,
                        contesto_sezione=r.contesto_sezione,
                        decisione=ImportRowDecisione.PENDING,
                    )
                    for r in result.rows
                ])

            messages.success(
                request,
                f"File caricato: {len(result.rows)} righe lette da '{result.sheet_name}'.",
            )
            return redirect("importazione:detail", pk=sessione.pk)
    else:
        form = ImportSessionUploadForm()

    return render(request, "importazione/session_form.html", {"form": form})


@login_required
def session_detail(request, pk: int):
    """Anteprima righe parsate. Mapping/match/apply verranno aggiunti negli step successivi."""
    sessione = get_object_or_404(
        ImportSession.objects.select_related("creato_da"), pk=pk
    )
    righe = sessione.righe.all()[:200]
    return render(
        request,
        "importazione/session_detail.html",
        {
            "sessione": sessione,
            "righe": righe,
            "totale_righe": sessione.righe.count(),
            "colonne": (sessione.riepilogo or {}).get("columns_detected", []),
        },
    )


@login_required
def session_delete(request, pk: int):
    sessione = get_object_or_404(ImportSession, pk=pk)
    if request.method == "POST":
        nome = sessione.nome
        sessione.delete()
        messages.success(request, f"Sessione '{nome}' eliminata.")
        return redirect(reverse("importazione:list"))
    return render(
        request, "importazione/session_confirm_delete.html", {"sessione": sessione}
    )
