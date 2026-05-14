"""Motore di matching delle ImportRow con le Anagrafiche esistenti.

Cascata di confidenza (in ordine): la prima che produce un match vince.

  1. codice_cli                 conf=1.00  metodo='codice_cli'
  2. codice_multi               conf=1.00  metodo='codice_multi'
  3. codice_gstudio             conf=1.00  metodo='codice_gstudio'
  4. codice_fiscale             conf=1.00  metodo='codice_fiscale'
  5. partita_iva                conf=1.00  metodo='partita_iva'
  6. denominazione esatta norm. conf=0.99  metodo='denominazione_esatta'
  7. alias esatto               conf=0.95  metodo='alias'
  8. fuzzy denominazione        conf=0.85+ metodo='fuzzy'

Convenzione decisioni:
- conf >= 0.99            -> ImportRowDecisione.AUTO_MATCH (l'utente puo'
                              comunque sovrascrivere)
- 0.85 <= conf < 0.99     -> ImportRowDecisione.PENDING (richiede conferma)
- nessun match            -> PENDING (utente sceglie crea/skip/manuale)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from anagrafica.models import Anagrafica

from .models import (
    AnagraficaAlias,
    ImportRow,
    ImportRowDecisione,
    ImportSession,
)


# ---------------------------------------------------------------------------
# Normalizzazione
# ---------------------------------------------------------------------------

_SUFFIX_SOCIETARI = re.compile(
    r"\b(S\.?\s*R\.?\s*L\.?|S\.?\s*P\.?\s*A\.?|S\.?\s*N\.?\s*C\.?|"
    r"S\.?\s*A\.?\s*S\.?|& C\.?|& F\.?LLI|S\.?\s*S\.?)\b",
    re.IGNORECASE,
)
_PARENS = re.compile(r"\([^)]*\)")
_NON_ALNUM = re.compile(r"[^A-Z0-9 ]+")
_MULTISPACE = re.compile(r"\s+")


def normalize_denominazione(s: str) -> str:
    """Normalizza una denominazione per confronti esatti/fuzzy."""
    if not s:
        return ""
    if str(s).strip() in _GARBAGE_VALUES:
        return ""
    out = s.upper()
    out = _PARENS.sub(" ", out)
    out = _SUFFIX_SOCIETARI.sub(" ", out)
    out = _NON_ALNUM.sub(" ", out)
    out = _MULTISPACE.sub(" ", out).strip()
    return out


# Valori "spazzatura" Excel da trattare come stringa vuota.
# Allineato con `importazione.apply._GARBAGE_VALUES`.
_GARBAGE_VALUES = frozenset({
    "#N/A", "#NA", "#NUM!", "#NULL!", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?",
    "N/A", "NA", "NULL", "null", "None", "-", "—", "–", "n.d.", "N.D.", "nd",
})


def _clean_codice(value: str) -> str:
    """Rimuove decimali e spazi da un codice (es. '266.0' -> '266').
    Restituisce '' anche per i placeholder spazzatura tipo '#N/A'."""
    if not value:
        return ""
    v = str(value).strip()
    if v in _GARBAGE_VALUES:
        return ""
    if v.endswith(".0"):
        v = v[:-2]
    return v


# ---------------------------------------------------------------------------
# Risultato match e parametri
# ---------------------------------------------------------------------------

FUZZY_SOGLIA = 85  # rapidfuzz score 0-100; sotto soglia = nessun match fuzzy


@dataclass
class MatchResult:
    anagrafica: Anagrafica | None
    confidenza: float
    metodo: str

    @property
    def trovato(self) -> bool:
        return self.anagrafica is not None


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def _by_field(qs, field: str, value: str) -> Anagrafica | None:
    if not value:
        return None
    return qs.filter(**{field: value}).first()


def _by_alias(value: str) -> Anagrafica | None:
    if not value:
        return None
    a = AnagraficaAlias.objects.select_related("anagrafica").filter(
        denominazione_alias=value
    ).first()
    return a.anagrafica if a else None


# ---------------------------------------------------------------------------
# Cache anagrafiche per la sessione (evita N query per riga)
# ---------------------------------------------------------------------------

@dataclass
class AnagraficaIndex:
    """Indici in-memory per le anagrafiche attive (non eliminate).

    Costruito una volta per sessione di matching: ~poche centinaia/migliaia
    di righe massimo. Per ogni codice univoco: dict diretto.
    """

    by_cli: dict[str, Anagrafica]
    by_multi: dict[str, Anagrafica]
    by_gstudio: dict[str, Anagrafica]
    by_cf: dict[str, Anagrafica]
    by_piva: dict[str, Anagrafica]
    by_denom_norm: dict[str, Anagrafica]
    by_alias_norm: dict[str, Anagrafica]
    denoms: list[tuple[str, Anagrafica]]  # per fuzzy

    @classmethod
    def build(cls) -> "AnagraficaIndex":
        qs = Anagrafica.objects.filter(is_deleted=False).only(
            "id",
            "denominazione",
            "codice_cli",
            "codice_multi",
            "codice_gstudio",
            "codice_fiscale",
            "partita_iva",
        )
        by_cli, by_multi, by_gstudio = {}, {}, {}
        by_cf, by_piva, by_denom_norm = {}, {}, {}
        denoms = []
        for a in qs:
            if a.codice_cli:
                by_cli[a.codice_cli] = a
            if a.codice_multi:
                by_multi[a.codice_multi] = a
            if a.codice_gstudio:
                by_gstudio[a.codice_gstudio] = a
            if a.codice_fiscale:
                by_cf[a.codice_fiscale.upper()] = a
            if a.partita_iva:
                by_piva[a.partita_iva] = a
            norm = normalize_denominazione(a.denominazione)
            if norm:
                # In caso di duplicati di denominazione normalizzata vince il
                # primo: il match esatto smette di essere autoritativo, e si
                # finisce nel fuzzy/manuale. Coerente con l'aspettativa.
                by_denom_norm.setdefault(norm, a)
                denoms.append((norm, a))

        by_alias_norm: dict[str, Anagrafica] = {}
        for al in AnagraficaAlias.objects.select_related("anagrafica"):
            by_alias_norm.setdefault(
                normalize_denominazione(al.denominazione_alias),
                al.anagrafica,
            )

        return cls(
            by_cli=by_cli,
            by_multi=by_multi,
            by_gstudio=by_gstudio,
            by_cf=by_cf,
            by_piva=by_piva,
            by_denom_norm=by_denom_norm,
            by_alias_norm=by_alias_norm,
            denoms=denoms,
        )


# ---------------------------------------------------------------------------
# Matching core
# ---------------------------------------------------------------------------

def _value_for(mapping: dict[str, str], target: str, dati: dict) -> str:
    """Ritorna il valore di una colonna del file mappata sul `target` indicato."""
    for col, t in mapping.items():
        if t == target:
            return _clean_codice(dati.get(col, ""))
    return ""


def match_row(
    dati: dict,
    mapping: dict[str, str],
    index: AnagraficaIndex,
) -> MatchResult:
    # 1-5: codici univoci
    cli = _value_for(mapping, "codice_cli", dati)
    if cli and cli in index.by_cli:
        return MatchResult(index.by_cli[cli], 1.0, "codice_cli")

    multi = _value_for(mapping, "codice_multi", dati)
    if multi and multi in index.by_multi:
        return MatchResult(index.by_multi[multi], 1.0, "codice_multi")

    gstu = _value_for(mapping, "codice_gstudio", dati)
    if gstu and gstu in index.by_gstudio:
        return MatchResult(index.by_gstudio[gstu], 1.0, "codice_gstudio")

    cf = _value_for(mapping, "codice_fiscale", dati).upper()
    if cf and cf in index.by_cf:
        return MatchResult(index.by_cf[cf], 1.0, "codice_fiscale")

    piva = _value_for(mapping, "partita_iva", dati)
    if piva and piva in index.by_piva:
        return MatchResult(index.by_piva[piva], 1.0, "partita_iva")

    # 6-7-8: denominazione
    denom_raw = _value_for(mapping, "denominazione", dati)
    norm = normalize_denominazione(denom_raw)
    if not norm:
        return MatchResult(None, 0.0, "")

    if norm in index.by_denom_norm:
        return MatchResult(index.by_denom_norm[norm], 0.99, "denominazione_esatta")
    if norm in index.by_alias_norm:
        return MatchResult(index.by_alias_norm[norm], 0.95, "alias")

    # 8: fuzzy. process.extractOne ritorna (match_str, score, idx).
    if index.denoms:
        choices = [d[0] for d in index.denoms]
        result = process.extractOne(
            norm, choices, scorer=fuzz.WRatio, score_cutoff=FUZZY_SOGLIA
        )
        if result is not None:
            _, score, idx = result
            return MatchResult(index.denoms[idx][1], score / 100.0, "fuzzy")

    return MatchResult(None, 0.0, "")


# ---------------------------------------------------------------------------
# Apply su sessione
# ---------------------------------------------------------------------------

@dataclass
class MatchStats:
    auto_match: int = 0
    pending: int = 0
    nessun_match: int = 0
    metodi: dict[str, int] | None = None

    def to_dict(self) -> dict:
        return {
            "auto_match": self.auto_match,
            "pending": self.pending,
            "nessun_match": self.nessun_match,
            "metodi": self.metodi or {},
        }


AUTO_MATCH_THRESHOLD = 0.99


def run_matching(sessione: ImportSession) -> MatchStats:
    """Esegue il matching su tutte le righe non ancora confermate manualmente.

    Le righe con decisione CONFERMATO/NUOVA/SKIP non vengono toccate
    (sono scelte esplicite dell'utente). Le altre (PENDING / AUTO_MATCH /
    ERRORE) vengono ricalcolate.
    """
    index = AnagraficaIndex.build()
    mapping = sessione.column_mapping or {}
    stats = MatchStats(metodi={})

    righe = sessione.righe.exclude(
        decisione__in=[
            ImportRowDecisione.CONFERMATO,
            ImportRowDecisione.NUOVA,
            ImportRowDecisione.SKIP,
        ]
    )

    da_aggiornare: list[ImportRow] = []
    for r in righe:
        res = match_row(r.dati_grezzi, mapping, index)
        r.anagrafica_match = res.anagrafica
        r.confidenza = res.confidenza
        r.metodo_match = res.metodo
        if res.trovato and res.confidenza >= AUTO_MATCH_THRESHOLD:
            r.decisione = ImportRowDecisione.AUTO_MATCH
            stats.auto_match += 1
        elif res.trovato:
            r.decisione = ImportRowDecisione.PENDING
            stats.pending += 1
        else:
            r.decisione = ImportRowDecisione.PENDING
            stats.nessun_match += 1
        if res.metodo:
            stats.metodi[res.metodo] = stats.metodi.get(res.metodo, 0) + 1
        da_aggiornare.append(r)

    ImportRow.objects.bulk_update(
        da_aggiornare,
        fields=["anagrafica_match", "confidenza", "metodo_match", "decisione"],
        batch_size=500,
    )
    return stats
