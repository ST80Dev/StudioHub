from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from anagrafica.models import Anagrafica

from .fields import (
    ANAGRAFICA_FIELDS_GROUPS,
    EXTRA_SUGGESTED,
    is_valid_target,
)
from .forms import ImportSessionUploadForm
from .matching import run_matching
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


def _filter_decisione(qs, decisione: str):
    if decisione in {c.value for c in ImportRowDecisione}:
        return qs.filter(decisione=decisione)
    return qs


@login_required
def session_detail(request, pk: int):
    sessione = get_object_or_404(
        ImportSession.objects.select_related("creato_da"), pk=pk
    )
    decisione_filter = request.GET.get("decisione", "")
    righe_qs = sessione.righe.select_related("anagrafica_match")
    righe_qs = _filter_decisione(righe_qs, decisione_filter)

    counts = dict.fromkeys([d.value for d in ImportRowDecisione], 0)
    for d in sessione.righe.values_list("decisione", flat=True):
        counts[d] = counts.get(d, 0) + 1

    return render(
        request,
        "importazione/session_detail.html",
        {
            "sessione": sessione,
            "righe": righe_qs[:300],
            "totale_righe": sessione.righe.count(),
            "colonne": (sessione.riepilogo or {}).get("columns_detected", []),
            "counts": counts,
            "decisione_filter": decisione_filter,
            "ImportRowDecisione": ImportRowDecisione,
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
@require_POST
def session_run_matching(request, pk: int):
    sessione = get_object_or_404(ImportSession, pk=pk)
    stats = run_matching(sessione)
    sessione.riepilogo = {
        **(sessione.riepilogo or {}),
        "match_stats": stats.to_dict(),
    }
    if sessione.stato == ImportSessionStato.BOZZA:
        sessione.stato = ImportSessionStato.MAPPATA
    sessione.save(update_fields=["riepilogo", "stato"])
    messages.success(
        request,
        f"Matching eseguito: {stats.auto_match} auto-match, "
        f"{stats.pending} da rivedere, {stats.nessun_match} senza candidato.",
    )
    return redirect("importazione:detail", pk=pk)


@login_required
@require_POST
def row_update(request, pk: int):
    """Aggiorna decisione + anagrafica_match di una riga.

    POST: decisione, anagrafica_id (opz.).
    Risponde con il fragment `_row.html` per HTMX swap.
    """
    riga = get_object_or_404(ImportRow.objects.select_related("anagrafica_match"), pk=pk)
    decisione = request.POST.get("decisione", "").strip()
    anagrafica_id = request.POST.get("anagrafica_id", "").strip()

    if decisione and decisione not in {c.value for c in ImportRowDecisione}:
        return HttpResponse("Decisione non valida", status=400)

    if anagrafica_id:
        riga.anagrafica_match = get_object_or_404(Anagrafica, pk=anagrafica_id)
        if not decisione:
            decisione = ImportRowDecisione.CONFERMATO
        riga.metodo_match = "manuale"
        riga.confidenza = 1.0
    elif decisione == ImportRowDecisione.NUOVA:
        riga.anagrafica_match = None
    elif decisione == ImportRowDecisione.SKIP:
        # Manteniamo il match suggerito ma marchiamo skip.
        pass

    if decisione:
        riga.decisione = decisione
    riga.save(update_fields=[
        "anagrafica_match", "metodo_match", "confidenza", "decisione"
    ])

    return render(
        request,
        "importazione/_row.html",
        {
            "r": riga,
            "colonne": (riga.sessione.riepilogo or {}).get("columns_detected", []),
            "sessione": riga.sessione,
            "ImportRowDecisione": ImportRowDecisione,
        },
    )


@login_required
def anagrafica_search(request):
    """Endpoint JSON per autocomplete anagrafiche (live search)."""
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"results": []})
    qs = Anagrafica.objects.filter(is_deleted=False).filter(
        Q(denominazione__icontains=q)
        | Q(codice_cli__iexact=q)
        | Q(codice_multi__iexact=q)
        | Q(codice_gstudio__iexact=q)
        | Q(codice_fiscale__iexact=q.upper())
        | Q(partita_iva__iexact=q)
    ).order_by("denominazione")[:20]
    return JsonResponse({
        "results": [
            {
                "id": a.id,
                "label": f"{a.denominazione}",
                "sublabel": " · ".join(filter(None, [
                    a.codice_cli and f"CLI {a.codice_cli}",
                    a.codice_multi and f"MULTI {a.codice_multi}",
                    a.partita_iva and f"P.IVA {a.partita_iva}",
                    a.codice_fiscale and f"CF {a.codice_fiscale}",
                ])),
            }
            for a in qs
        ]
    })


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
