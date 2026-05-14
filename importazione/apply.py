"""Step 4: applicazione transazionale di una sessione di import sull'anagrafica.

Per ogni `ImportRow` con decisione `AUTO_MATCH` / `CONFERMATO` aggiorna l'anagrafica
matchata; con decisione `NUOVA` (e solo se `sessione.consente_creazione`) crea una
nuova `Anagrafica`; `SKIP` viene ignorata. I valori vanno presi dal `dati_grezzi`
della riga e mappati secondo `sessione.column_mapping`:

- target che è un campo di `Anagrafica` → setattr con il valore parsato
- target `extra:<chiave>` → upsert `DatoImportato(anagrafica, chiave, valore,
  fonte_session=sessione)`
- contesto sezione (tipo_soggetto / regime_contabile / contabilita) usato come
  fallback se NON è stato mappato esplicitamente nel file
- regola speciale `extra:ces_acq`: oltre a salvare il dato grezzo, prova a
  parsare valori tipo `C25` (cessato 2025) / `A25` (attivato 2025) e popola
  `stato` / `data_inizio_mandato` / `data_fine_mandato`

Ogni riga è applicata in un savepoint dedicato: se fallisce viene marcata
`ERRORE` con `messaggio_errore` ma la sessione complessiva prosegue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from anagrafica.models import (
    Anagrafica,
    AnagraficaReferenteStudio,
    GestioneContabilita,
    PeriodicitaIVA,
    RegimeContabile,
    RuoloReferenteStudio,
    StatoAnagrafica,
    TipoSoggetto,
)

from .models import (
    AnagraficaAlias,
    DatoImportato,
    ImportRow,
    ImportRowDecisione,
    ImportSession,
    ImportSessionStato,
)


# ---------------------------------------------------------------------------
# Helpers di parsing valori
# ---------------------------------------------------------------------------

# Valori "spazzatura" prodotti tipicamente da Excel quando una formula non
# si risolve, o quando il foglio originale ha celle vuote codificate con
# placeholder testuali. Vengono trattati come stringhe vuote prima di
# qualsiasi normalizzazione/persistenza.
_GARBAGE_VALUES = frozenset({
    "#N/A", "#NA", "#NUM!", "#NULL!", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?",
    "N/A", "NA", "NULL", "null", "None", "-", "—", "–", "n.d.", "N.D.", "nd",
})


def _is_garbage(value) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    return s == "" or s in _GARBAGE_VALUES


_DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%Y-%m-%d", "%Y/%m/%d",
    "%d/%m/%y",
)


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    # Caso comune: openpyxl restituisce direttamente datetime
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _parse_bool(value: str) -> bool | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in {"true", "1", "si", "sì", "yes", "y", "x", "vero"}:
        return True
    if v in {"false", "0", "no", "n", "falso", ""}:
        return False
    return None


def _parse_int(value: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        v = str(value).strip()
        if v.endswith(".0"):
            v = v[:-2]
        return int(v)
    except (ValueError, TypeError):
        return None


def _norm_choice(value: str, choices: type) -> str:
    """Match case-insensitive con le choices Django text. Ritorna il valore
    canonico se trovato, altrimenti la stringa originale (sara' validata dopo)."""
    if not value:
        return ""
    v = str(value).strip().lower()
    for c in choices.choices:
        valore, label = c
        if v in {valore.lower(), label.lower()}:
            return valore
        # Match anche su prefisso label (es. "ORD" -> "ordinario")
        if label.lower().startswith(v) or valore.lower().startswith(v):
            return valore
    return v


# Campi Anagrafica e come trasformare il valore in input.
# Default: stringa "stripped".
_FIELD_TRANSFORMS = {
    "data_inizio_mandato": _parse_date,
    "data_fine_mandato": _parse_date,
    "sostituto_imposta": _parse_bool,
    "iscritto_cciaa": _parse_bool,
    "peso_contabilita": _parse_int,
    "regime_contabile": lambda v: _norm_choice(v, RegimeContabile),
    "periodicita_iva": lambda v: _norm_choice(v, PeriodicitaIVA),
    "contabilita": lambda v: _norm_choice(v, GestioneContabilita),
    "tipo_soggetto": lambda v: _norm_choice(v, TipoSoggetto),
    "stato": lambda v: _norm_choice(v, StatoAnagrafica),
    "codice_fiscale": lambda v: (str(v).strip().upper() if v else ""),
}


def _transform_value(target: str, raw: object) -> object:
    if raw is None:
        return None
    fn = _FIELD_TRANSFORMS.get(target)
    if fn:
        return fn(raw)
    v = str(raw).strip()
    return v


# ---------------------------------------------------------------------------
# Regole speciali
# ---------------------------------------------------------------------------

_CES_ACQ_RE = re.compile(r"^\s*([CA])\s*(\d{2,4})\s*$", re.IGNORECASE)


def _interpret_ces_acq(value: str) -> dict:
    """Da 'C25' o 'A25' (anche 'C2025') deduce:
       - C: stato=CESSATO, data_fine_mandato=YYYY-12-31
       - A: data_inizio_mandato=YYYY-01-01
       Restituisce {} se non parsabile."""
    if not value:
        return {}
    m = _CES_ACQ_RE.match(str(value))
    if not m:
        return {}
    lettera = m.group(1).upper()
    anno_raw = int(m.group(2))
    anno = anno_raw if anno_raw >= 100 else 2000 + anno_raw
    if lettera == "C":
        return {
            "stato": StatoAnagrafica.CESSATO,
            "data_fine_mandato": date(anno, 12, 31),
        }
    return {"data_inizio_mandato": date(anno, 1, 1)}


# ---------------------------------------------------------------------------
# Apply core
# ---------------------------------------------------------------------------

@dataclass
class ApplyStats:
    create: int = 0
    update: int = 0
    skip: int = 0
    errori: int = 0
    pending_lasciate: int = 0
    dati_importati: int = 0
    alias_creati: int = 0
    # Referenti: assegnati = AnagraficaReferenteStudio creati (utente risolto);
    # pending = nomi salvati come DatoImportato in attesa di risoluzione manuale.
    referenti_assegnati: int = 0
    referenti_pending: int = 0
    dettagli_errori: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "create": self.create,
            "update": self.update,
            "skip": self.skip,
            "errori": self.errori,
            "pending_lasciate": self.pending_lasciate,
            "dati_importati": self.dati_importati,
            "alias_creati": self.alias_creati,
            "referenti_assegnati": self.referenti_assegnati,
            "referenti_pending": self.referenti_pending,
            "dettagli_errori": self.dettagli_errori[:50],
        }


# Campi obbligatori per la creazione di una nuova Anagrafica.
# Tutti gli altri (denominazione, tipo_soggetto, ecc.) sono ammessi vuoti:
# l'utente puo' importare velocemente quanti piu' record possibili e poi
# completare i dati mancanti dalla lista clienti (filtro "Da completare"
# + inline edit + bulk update).
_REQUIRED_FOR_CREATE = ("codice_interno",)

# Codici univoci su cui fare pre-check prima di create. In caso di conflitto
# il valore in questione viene degradato a None sulla nuova anagrafica
# e l'evento viene registrato come `DatoImportato(chiave='import_warning')`.
# Cosi' l'import non si blocca per duplicati ma li traccia per l'audit.
_UNIQUE_CODE_FIELDS = ("codice_cli", "codice_fiscale", "partita_iva")

# Placeholder noti per P.IVA/CF: stringhe numeriche tipo "0", "00000000000"
# che non sono partite IVA reali. Trattati come vuoti su quei due campi.
_NUMERIC_PLACEHOLDERS = frozenset({"0", "00", "000", "0000", "00000",
                                    "000000", "0000000", "00000000",
                                    "000000000", "0000000000",
                                    "00000000000"})


# ---------------------------------------------------------------------------
# Referenti studio (target speciali del mapping)
# ---------------------------------------------------------------------------
#
# Target mappabili dal wizard: il valore della cella e' un nome/sigla che
# proviamo a risolvere contro `UtenteStudio`. Se riusciamo, creiamo
# direttamente la riga `AnagraficaReferenteStudio`. Altrimenti salviamo
# il valore originale come `DatoImportato(chiave=<target>_pending)`,
# recuperabile col management command `risolvi_referenti_pending` quando
# gli utenti saranno popolati.

_REFERENTE_TARGETS: dict[str, str] = {
    "referente_contabilita": RuoloReferenteStudio.REFERENTE_CONTABILITA,
    "referente_consulenza": RuoloReferenteStudio.REFERENTE_CONSULENZA,
}


def _match_utente(raw_name: str):
    """Prova a risolvere un nome (free-text dall'Excel) a un UtenteStudio.

    Strategia: confronto case-insensitive su `get_full_name()`, `username`,
    `last_name` da solo. Ritorna l'utente solo se UNA singola corrispondenza
    e' trovata; in caso di 0 match o ambiguita' (>1), ritorna None per non
    fare assegnazioni rischiose.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    s = (raw_name or "").strip()
    if not s:
        return None

    # Match esatto su username
    qs = User.objects.filter(is_active=True, username__iexact=s)
    if qs.count() == 1:
        return qs.first()

    # Match esatto su "Nome Cognome" / "Cognome Nome"
    parts = s.split()
    if len(parts) >= 2:
        first, last = parts[0], " ".join(parts[1:])
        qs = User.objects.filter(
            is_active=True, first_name__iexact=first, last_name__iexact=last,
        )
        if qs.count() == 1:
            return qs.first()
        qs = User.objects.filter(
            is_active=True, first_name__iexact=last, last_name__iexact=first,
        )
        if qs.count() == 1:
            return qs.first()

    # Match esatto su solo cognome (utile per file che riportano "Rossi")
    qs = User.objects.filter(is_active=True, last_name__iexact=s)
    if qs.count() == 1:
        return qs.first()

    return None


def _make_unique_codice_interno(base: str) -> str:
    """Restituisce un `codice_interno` libero a partire da `base`. Se `base`
    e' gia' usato aggiunge un suffisso `-2`, `-3`, ... finche' libero."""
    from anagrafica.models import Anagrafica as _A
    if not base:
        return base
    if not _A.objects.filter(codice_interno=base).exists():
        return base
    n = 2
    while _A.objects.filter(codice_interno=f"{base}-{n}").exists():
        n += 1
    return f"{base}-{n}"


def _build_anagrafica_payload(
    riga: ImportRow,
    mapping: dict[str, str],
    is_new: bool,
) -> tuple[dict, dict, dict]:
    """Restituisce (campi_anagrafica, extra_kv, ces_acq_derivati).

    Comportamento per mapping multipli (piu' colonne mappate sullo stesso
    target, es. due colonne entrambe mappate a `denominazione`):
    **vince il primo valore non spazzatura** trovato. Permette il fallback
    naturale DENOMINAZIONE -> RAG.SOC: se la prima e' vuota, l'altra
    viene usata automaticamente.

    Filtra i valori "spazzatura" tipici di Excel (#N/A, #NUM!, -, ecc.).
    Per i campi P.IVA/CF anche i placeholder numerici come "0" vengono
    trattati come vuoti.
    """
    anagrafica_fields: dict = {}
    extra_kv: dict = {}
    referenti_raw: dict = {}  # {target: raw_value} per i target _REFERENTE_TARGETS
    ces_derivati: dict = {}

    for col, target in mapping.items():
        if not target:
            continue
        raw = (riga.dati_grezzi or {}).get(col, "")
        if _is_garbage(raw):
            continue
        if target.startswith("extra:"):
            chiave = target[len("extra:"):]
            # setdefault: vince il primo valore non vuoto per chiave
            extra_kv.setdefault(chiave, str(raw).strip())
            if chiave == "ces_acq" and not ces_derivati:
                ces_derivati.update(_interpret_ces_acq(raw))
            continue
        # Target speciali "referente_*": non sono campi di Anagrafica,
        # vengono gestiti dopo il save (vedi _apply_referenti).
        if target in _REFERENTE_TARGETS:
            referenti_raw.setdefault(target, str(raw).strip())
            continue
        val = _transform_value(target, raw)
        if val is None or val == "":
            continue
        # Placeholder numerici per i campi codice fiscale / partita IVA.
        if target in ("codice_fiscale", "partita_iva") and str(val).strip() in _NUMERIC_PLACEHOLDERS:
            continue
        # `setdefault`: primo non-vuoto wins (es. denominazione viene dalla
        # prima colonna mappata che ha valore valido).
        anagrafica_fields.setdefault(target, val)

    # Fallback dal contesto sezione: solo se NON mappato esplicitamente.
    ctx = riga.contesto_sezione or {}
    for f in ("tipo_soggetto", "regime_contabile", "contabilita"):
        if not anagrafica_fields.get(f) and ctx.get(f):
            anagrafica_fields[f] = ctx[f]

    # I valori derivati da CES/ACQ valgono come integrazione: non sovrascrivono
    # un valore esplicito sullo stesso campo.
    for f, v in ces_derivati.items():
        anagrafica_fields.setdefault(f, v)

    # Genera codice_interno se non presente: priorità a codice_cli, poi
    # codice_multi, poi un placeholder R<id_riga>. Garantito unico via
    # auto-suffix se necessario (gestito in _apply_single_row al momento
    # del create).
    if is_new:
        if not anagrafica_fields.get("codice_interno"):
            anagrafica_fields["codice_interno"] = (
                anagrafica_fields.get("codice_cli")
                or anagrafica_fields.get("codice_multi")
                or f"R{riga.pk}"
            )

    return anagrafica_fields, extra_kv, ces_derivati, referenti_raw


def _apply_referenti(
    anagrafica: Anagrafica,
    referenti_raw: dict,
    sessione: ImportSession,
    stats: ApplyStats,
) -> None:
    """Per ogni target referente:
    - se il nome si risolve a un singolo UtenteStudio, upsert
      AnagraficaReferenteStudio (idempotente: niente duplicati per
      anagrafica/utente/ruolo se gia' attivo).
    - altrimenti salva il nome come DatoImportato con chiave
      `<target>_pending` (recuperabile con management command).
    """
    for target, raw_value in referenti_raw.items():
        if not raw_value:
            continue
        ruolo = _REFERENTE_TARGETS[target]
        utente = _match_utente(raw_value)
        if utente is not None:
            already = AnagraficaReferenteStudio.objects.filter(
                anagrafica=anagrafica,
                utente=utente,
                ruolo=ruolo,
                data_fine__isnull=True,
            ).exists()
            if not already:
                AnagraficaReferenteStudio.objects.create(
                    anagrafica=anagrafica,
                    utente=utente,
                    ruolo=ruolo,
                    data_inizio=date.today(),
                )
                stats.referenti_assegnati += 1
        else:
            DatoImportato.objects.update_or_create(
                anagrafica=anagrafica,
                chiave=f"{target}_pending",
                fonte_session=sessione,
                defaults={"valore": raw_value},
            )
            stats.referenti_pending += 1


def _apply_single_row(riga: ImportRow, sessione: ImportSession, stats: ApplyStats) -> None:
    mapping = sessione.column_mapping or {}
    decisione = riga.decisione

    if decisione == ImportRowDecisione.SKIP:
        stats.skip += 1
        return
    if decisione in (ImportRowDecisione.PENDING, ImportRowDecisione.ERRORE):
        stats.pending_lasciate += 1
        return

    # Solo confermato/auto_match/nuova proseguono.
    is_new = decisione == ImportRowDecisione.NUOVA
    if is_new and not sessione.consente_creazione:
        riga.decisione = ImportRowDecisione.ERRORE
        riga.messaggio_errore = "Sessione non abilitata alla creazione di nuove anagrafiche."
        riga.save(update_fields=["decisione", "messaggio_errore"])
        stats.errori += 1
        stats.dettagli_errori.append(f"#{riga.numero_riga}: creazione non consentita")
        return
    if not is_new and not riga.anagrafica_match_id:
        riga.decisione = ImportRowDecisione.ERRORE
        riga.messaggio_errore = "Decisione conferma ma nessuna anagrafica abbinata."
        riga.save(update_fields=["decisione", "messaggio_errore"])
        stats.errori += 1
        stats.dettagli_errori.append(f"#{riga.numero_riga}: match mancante")
        return

    payload, extra_kv, _, referenti_raw = _build_anagrafica_payload(
        riga, mapping, is_new=is_new
    )

    # `codice_cli` e' unique nullable: una stringa vuota o garbage va
    # convertita in None per evitare il conflitto con altre righe "vuote".
    if "codice_cli" in payload and not payload["codice_cli"]:
        payload["codice_cli"] = None

    # Warning da memorizzare come DatoImportato dopo la create (campo per campo).
    import_warnings: list[str] = []

    try:
        with transaction.atomic():
            if is_new:
                # Validazione minima per creazione.
                missing = [k for k in _REQUIRED_FOR_CREATE if not payload.get(k)]
                if missing:
                    raise ValueError(
                        f"Campi obbligatori mancanti: {', '.join(missing)}"
                    )
                # Pre-check conflitti su codici univoci: invece di bloccare,
                # degradiamo il valore a None sulla nuova anagrafica e teniamo
                # traccia del conflitto come `DatoImportato`. L'utente potra'
                # poi decidere cosa fare (es. fondere i due record).
                for code_field in _UNIQUE_CODE_FIELDS:
                    code_value = payload.get(code_field)
                    if not code_value:
                        continue
                    existing = (
                        Anagrafica.objects.filter(**{code_field: code_value})
                        .filter(is_deleted=False)
                        .exclude(pk=getattr(riga.anagrafica_match, "pk", -1))
                        .first()
                    )
                    if existing:
                        import_warnings.append(
                            f"{code_field}={code_value!r} non importato: "
                            f"già in uso da '{existing.denominazione}' (id {existing.pk})"
                        )
                        # codice_cli e' nullable: setta None. codice_fiscale
                        # e partita_iva non sono nullable -> stringa vuota.
                        payload[code_field] = None if code_field == "codice_cli" else ""

                # Garantisci unicita' del codice_interno con auto-suffix.
                payload["codice_interno"] = _make_unique_codice_interno(
                    str(payload.get("codice_interno") or f"R{riga.pk}")
                )
                anagrafica = Anagrafica.objects.create(**payload)
                stats.create += 1
            else:
                anagrafica = riga.anagrafica_match
                for k, v in payload.items():
                    # Non sovrascrivere il codice_interno esistente.
                    if k == "codice_interno":
                        continue
                    setattr(anagrafica, k, v)
                anagrafica.save()
                stats.update += 1

            # Extra → DatoImportato (upsert per (anagrafica, chiave, sessione))
            for chiave, val in extra_kv.items():
                DatoImportato.objects.update_or_create(
                    anagrafica=anagrafica,
                    chiave=chiave,
                    fonte_session=sessione,
                    defaults={"valore": val},
                )
                stats.dati_importati += 1

            # Referenti studio (target speciali): risolve nome -> UtenteStudio
            # oppure salva come DatoImportato `_pending` per backfill manuale.
            if referenti_raw:
                _apply_referenti(anagrafica, referenti_raw, sessione, stats)

            # Warning di import: codici univoci in conflitto degradati a vuoto.
            # Memorizzati in DatoImportato per audit successivo. La constraint
            # UniqueConstraint(anagrafica, chiave, fonte_session) richiede una
            # sola riga per chiave; concateniamo i warning con newline.
            if import_warnings:
                DatoImportato.objects.update_or_create(
                    anagrafica=anagrafica,
                    chiave="import_warning",
                    fonte_session=sessione,
                    defaults={"valore": "\n".join(import_warnings)},
                )

            # Alias: se il file ha una denominazione diversa da quella dell'anagrafica
            # esistente, registriamola per i futuri match.
            denom_file = payload.get("denominazione") or ""
            if (
                denom_file
                and not is_new
                and denom_file.strip().upper() != (anagrafica.denominazione or "").strip().upper()
            ):
                _, created = AnagraficaAlias.objects.get_or_create(
                    anagrafica=anagrafica,
                    denominazione_alias=denom_file.strip(),
                    defaults={"fonte": f"import:{sessione.pk}"},
                )
                if created:
                    stats.alias_creati += 1

            # Aggiorna la riga: collega l'anagrafica creata e mantieni la
            # decisione (NUOVA resta NUOVA per audit; conferma resta conferma).
            riga.anagrafica_match = anagrafica
            riga.save(update_fields=["anagrafica_match"])
    except (IntegrityError, ValueError) as exc:
        riga.decisione = ImportRowDecisione.ERRORE
        riga.messaggio_errore = str(exc)[:500]
        riga.save(update_fields=["decisione", "messaggio_errore"])
        stats.errori += 1
        stats.dettagli_errori.append(f"#{riga.numero_riga}: {exc}")


@dataclass
class ApplyPreview:
    da_creare: int = 0
    da_aggiornare: int = 0
    da_saltare: int = 0
    pending: int = 0
    consente_creazione: bool = False
    blocchi: list[str] = field(default_factory=list)

    @property
    def ha_bloccanti(self) -> bool:
        return bool(self.blocchi)


def preview_apply(sessione: ImportSession) -> ApplyPreview:
    """Riepilogo dry-run prima dell'apply. Non scrive nulla."""
    p = ApplyPreview(consente_creazione=sessione.consente_creazione)
    for r in sessione.righe.all():
        if r.decisione == ImportRowDecisione.NUOVA:
            p.da_creare += 1
        elif r.decisione in (ImportRowDecisione.AUTO_MATCH, ImportRowDecisione.CONFERMATO):
            p.da_aggiornare += 1
        elif r.decisione == ImportRowDecisione.SKIP:
            p.da_saltare += 1
        else:
            p.pending += 1
    if p.da_creare > 0 and not sessione.consente_creazione:
        p.blocchi.append(
            f"{p.da_creare} righe sono marcate 'crea nuova' ma la sessione "
            f"non consente la creazione di anagrafiche."
        )
    if not (sessione.column_mapping or {}):
        p.blocchi.append("Nessuna colonna mappata: imposta il mapping prima di applicare.")
    return p


def run_apply(sessione: ImportSession) -> ApplyStats:
    """Esegue l'apply. Atomico per riga (savepoint), non per sessione."""
    stats = ApplyStats()
    for riga in sessione.righe.select_related("anagrafica_match").all():
        _apply_single_row(riga, sessione, stats)

    sessione.stato = ImportSessionStato.APPLICATA
    sessione.applied_at = timezone.now()
    sessione.riepilogo = {
        **(sessione.riepilogo or {}),
        "apply_stats": stats.to_dict(),
    }
    sessione.save(update_fields=["stato", "applied_at", "riepilogo"])
    return stats
