from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .fields import (
    ANAGRAFICA_FIELDS_GROUPS,
    EXTRA_SUGGESTED,
    is_valid_target,
)
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
def session_mapping_edit(request, pk: int):
    """Step 2: editor del mapping colonne -> campi target.

    Su POST salva column_mapping. Lato client il select consente di scegliere
    fra i campi Anagrafica e i suggerimenti `extra:*`; chi vuole una chiave
    extra arbitraria la digita nel campo `extra_<i>` accanto al select.
    """
    sessione = get_object_or_404(ImportSession, pk=pk)
    colonne: list[str] = (sessione.riepilogo or {}).get("columns_detected", [])
    mapping_attuale = dict(sessione.column_mapping or {})

    if request.method == "POST":
        nuovo_mapping: dict[str, str] = {}
        errori: list[str] = []
        for i, col in enumerate(colonne):
            target = (request.POST.get(f"target_{i}") or "").strip()
            extra_custom = (request.POST.get(f"extra_{i}") or "").strip()
            # Se l'utente ha scritto un extra custom, vince sul select.
            if extra_custom:
                target = f"extra:{extra_custom}"
            if not is_valid_target(target):
                errori.append(f"Colonna '{col}': destinazione '{target}' non valida.")
                continue
            if target:
                nuovo_mapping[col] = target

        if errori:
            for e in errori:
                messages.error(request, e)
        else:
            sessione.column_mapping = nuovo_mapping
            sessione.save(update_fields=["column_mapping"])
            messages.success(
                request,
                f"Mapping aggiornato ({len(nuovo_mapping)} colonne mappate, "
                f"{len(colonne) - len(nuovo_mapping)} ignorate).",
            )
            return redirect("importazione:detail", pk=sessione.pk)
        # In caso di errori, ricarico il form con i valori inviati.
        mapping_attuale = {col: (request.POST.get(f"target_{i}") or "").strip()
                           for i, col in enumerate(colonne)}

    # Costruisco i sample (primo valore non vuoto per ogni colonna), utile a
    # riconoscere a vista il contenuto della colonna nel form.
    sample_values: dict[str, str] = {}
    for r in sessione.righe.values_list("dati_grezzi", flat=True)[:50]:
        for col in colonne:
            v = (r or {}).get(col, "")
            if v and col not in sample_values:
                sample_values[col] = str(v)
        if len(sample_values) == len(colonne):
            break

    rows_form = []
    for i, col in enumerate(colonne):
        target = mapping_attuale.get(col, "")
        # Se è una chiave extra non in EXTRA_SUGGESTED, la prepopolo nel campo libero.
        extra_custom = ""
        if target.startswith("extra:") and (target not in {v for v, _ in EXTRA_SUGGESTED}):
            extra_custom = target[len("extra:"):]
            target = ""  # il select rimane vuoto, vince il campo libero
        rows_form.append({
            "index": i,
            "col": col,
            "sample": sample_values.get(col, ""),
            "target": target,
            "extra_custom": extra_custom,
        })

    return render(
        request,
        "importazione/session_mapping.html",
        {
            "sessione": sessione,
            "rows": rows_form,
            "anagrafica_groups": ANAGRAFICA_FIELDS_GROUPS,
            "extra_suggested": EXTRA_SUGGESTED,
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
