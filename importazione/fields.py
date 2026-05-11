"""Catalogo dei campi target su cui mappare le colonne dei file importati.

Usato dall'editor di mapping (step 2) per popolare le opzioni del select.
Centralizzato qui per non sparpagliare la lista nei template.
"""

# Campi Anagrafica esposti come target di mapping, raggruppati per UI.
# Format: (gruppo, [(valore, label), ...]).
ANAGRAFICA_FIELDS_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Identificativi",
        [
            ("codice_interno", "Codice interno (chiave studio)"),
            ("codice_cli", "COD CLI ANA"),
            ("codice_multi", "COD MULTI"),
            ("codice_gstudio", "COD GSTU"),
            ("codice_fiscale", "Codice fiscale"),
            ("partita_iva", "Partita IVA"),
        ],
    ),
    (
        "Anagrafica",
        [
            ("denominazione", "Denominazione / Ragione sociale"),
            ("cognome", "Cognome (PF)"),
            ("nome", "Nome (PF)"),
            ("tipo_soggetto", "Tipo soggetto"),
            ("email", "Email"),
        ],
    ),
    (
        "Indirizzo",
        [
            ("indirizzo_via", "Via"),
            ("indirizzo_civico", "Civico"),
            ("indirizzo_cap", "CAP"),
            ("indirizzo_comune", "Comune"),
            ("indirizzo_provincia", "Provincia"),
            ("indirizzo_nazione", "Nazione"),
        ],
    ),
    (
        "Fiscale operativo",
        [
            ("regime_contabile", "Regime contabile"),
            ("periodicita_iva", "Periodicità IVA"),
            ("contabilita", "Tenuta contabilità (interna/esterna)"),
            ("categoria_professione", "Categoria professione"),
            ("data_fine_esercizio", "Fine esercizio (MM-DD)"),
            ("sostituto_imposta", "Sostituto d'imposta"),
            ("iscritto_cciaa", "Iscritto CCIAA"),
            ("peso_contabilita", "Peso contabilità"),
        ],
    ),
    (
        "Stato e date",
        [
            ("stato", "Stato (attivo/sospeso/cessato)"),
            ("data_inizio_mandato", "Inizio mandato"),
            ("data_fine_mandato", "Fine mandato"),
            ("note", "Note"),
        ],
    ),
]

# Chiavi extra (DatoImportato) suggerite — usate per i campi non promossi
# a colonna su Anagrafica (es. addetto consulenza, gruppo familiare, ecc.).
# L'utente puo' comunque digitarne di nuove (form a testo libero).
EXTRA_SUGGESTED: list[tuple[str, str]] = [
    ("extra:gruppo", "Gruppo familiare/società"),
    ("extra:pec", "PEC"),
    ("extra:addetto_consulenza", "Addetto consulenza"),
    ("extra:addetto_contabilita", "Addetto contabilità"),
    ("extra:ces_acq", "CES/ACQ (cessazione/acquisizione)"),
    ("extra:non_attive", "Flag non attive"),
    ("extra:anno_opzione", "Anno opzione regime"),
    ("extra:budget", "Budget"),
    ("extra:prima_nota", "Prima nota"),
    ("extra:pn", "PN"),
    ("extra:dir", "Direzione"),
]

SKIP_VALUE = ""  # stringa vuota = colonna ignorata


def all_anagrafica_targets() -> set[str]:
    return {v for _, fields in ANAGRAFICA_FIELDS_GROUPS for v, _ in fields}


def is_valid_target(target: str) -> bool:
    """Una destinazione è valida se è vuota (skip), un campo Anagrafica
    riconosciuto, o ha la forma `extra:<chiave>` con chiave non vuota."""
    if not target:
        return True
    if target.startswith("extra:"):
        chiave = target[len("extra:"):].strip()
        # consenti lettere, numeri, _ e - per le chiavi
        return bool(chiave) and all(
            c.isalnum() or c in "_-" for c in chiave
        )
    return target in all_anagrafica_targets()
