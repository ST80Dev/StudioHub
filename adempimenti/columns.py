"""Definizione del set standard di colonne riusabili nelle tabelle adempimenti.

Le tabelle adempimenti (LIPE, F24, IVA, dichiarativi, ecc.) condividono un
insieme di colonne base che provengono dall'anagrafica del cliente, piu' due
colonne comuni a tutti gli adempimenti (`stato`, `note`). Ogni nuova tabella
parte da questo set e puo' aggiungere colonne specifiche del proprio dominio
(es. Q1..Q4 per LIPE-anno, N° Fornitura per LIPE-trimestre).

La selezione delle colonne per ciascun `TipoAdempimentoCatalogo` e' configurabile
dall'admin tramite il modello `VistaAdempimentoColonne` (vedi `models.py`).
Se non c'e' una configurazione, si usa il `DEFAULT_COLUMN_CODES`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable


@dataclass(frozen=True)
class ColumnSpec:
    """Specifica dichiarativa di una colonna.

    - `code`: identificativo stabile (usato in DB/URL).
    - `label`: etichetta header estesa.
    - `label_short`: etichetta compatta per header denso.
    - `sort_field`: nome campo per `order_by()`. None = non ordinabile.
    - `filter_param`: nome query param per il filtro (es. `f_cf`). None = no filtro.
    - `filter_kind`: 'text' (input testo, submit con Invio) o 'select'
       (dropdown, submit on change) o None (no filtro).
    - `filter_choices_key`: chiave choices_labels per popolare il select.
    - `css_th`: classi CSS per il <th>.
    - `css_td`: classi CSS per il <td>.
    """

    code: str
    label: str
    label_short: str
    sort_field: str | None = None
    filter_param: str | None = None
    filter_kind: str | None = None  # 'text' | 'select'
    filter_choices_key: str | None = None
    css_th: str = "px-3 py-1"
    css_td: str = "px-3"


# Set completo delle colonne standard disponibili.
# Ogni codice qui sotto deve avere un blocco corrispondente nel partial
# `templates/adempimenti/cells/_cell.html` (dispatcher) per il rendering.
STANDARD_COLUMNS: dict[str, ColumnSpec] = {
    "cliente": ColumnSpec(
        code="cliente",
        label="Cliente",
        label_short="Cliente",
        sort_field="anagrafica__denominazione",
        filter_param="f_denominazione",
        filter_kind="text",
        css_th="px-3 py-1",
        css_td="px-3",
    ),
    "codice_interno": ColumnSpec(
        code="codice_interno",
        label="Codice",
        label_short="Cod",
        sort_field="anagrafica__codice_interno",
        filter_param="f_codice",
        filter_kind="text",
        css_th="px-3 py-1 w-24",
        css_td="px-3 font-mono text-xs",
    ),
    "codice_multi": ColumnSpec(
        code="codice_multi",
        label="Cod Multi",
        label_short="Multi",
        sort_field="anagrafica__codice_multi",
        filter_param="f_multi",
        filter_kind="text",
        css_th="px-3 py-1 w-24",
        css_td="px-3 font-mono text-xs",
    ),
    "codice_fiscale": ColumnSpec(
        code="codice_fiscale",
        label="Codice Fiscale",
        label_short="CF",
        sort_field="anagrafica__codice_fiscale",
        filter_param="f_cf",
        filter_kind="text",
        css_th="px-3 py-1 w-40",
        css_td="px-3 font-mono text-xs",
    ),
    "partita_iva": ColumnSpec(
        code="partita_iva",
        label="Partita IVA",
        label_short="P.IVA",
        sort_field="anagrafica__partita_iva",
        filter_param="f_piva",
        filter_kind="text",
        css_th="px-3 py-1 w-32",
        css_td="px-3 font-mono text-xs",
    ),
    "tipo_soggetto": ColumnSpec(
        code="tipo_soggetto",
        label="Tipo soggetto",
        label_short="Tipo",
        sort_field="anagrafica__tipo_soggetto",
        filter_param="f_tipo_sogg",
        filter_kind="select",
        filter_choices_key="tipo_soggetto",
        css_th="px-3 py-1",
        css_td="px-3 text-xs",
    ),
    "regime_contabile": ColumnSpec(
        code="regime_contabile",
        label="Regime",
        label_short="Regime",
        sort_field="anagrafica__regime_contabile",
        filter_param="f_regime",
        filter_kind="select",
        filter_choices_key="regime_contabile",
        css_th="px-3 py-1",
        css_td="px-3 text-xs",
    ),
    "tipo_contabilita": ColumnSpec(
        code="tipo_contabilita",
        label="Contabilità",
        label_short="Contab",
        sort_field="anagrafica__contabilita",
        filter_param="f_contab",
        filter_kind="select",
        filter_choices_key="contabilita",
        css_th="px-3 py-1",
        css_td="px-3 text-xs",
    ),
    "periodicita_iva": ColumnSpec(
        code="periodicita_iva",
        label="Periodicità IVA",
        label_short="IVA",
        sort_field="anagrafica__periodicita_iva",
        filter_param="f_iva",
        filter_kind="select",
        filter_choices_key="periodicita_iva",
        css_th="px-3 py-1",
        css_td="px-3 text-xs",
    ),
    "referente_contab": ColumnSpec(
        code="referente_contab",
        label="Addetto contab.",
        label_short="Contab",
        sort_field=None,  # M2M storicizzato, ordinamento via campo derivato (futuro)
        filter_param="f_ref_contab",
        filter_kind="text",
        css_th="px-3 py-1",
        css_td="px-3 text-xs",
    ),
    "referente_consul": ColumnSpec(
        code="referente_consul",
        label="Resp. consulenza",
        label_short="Consul",
        sort_field=None,
        filter_param="f_ref_consul",
        filter_kind="text",
        css_th="px-3 py-1",
        css_td="px-3 text-xs",
    ),
    "stato": ColumnSpec(
        code="stato",
        label="Stato",
        label_short="Stato",
        sort_field="stato",
        filter_param="f_stato",
        filter_kind="select",
        filter_choices_key="_stato_adempimento",  # speciale, da StatoAdempimento.choices
        css_th="px-3 py-1",
        css_td="px-3",
    ),
    "data_invio": ColumnSpec(
        code="data_invio",
        label="Data invio",
        label_short="Inv.",
        sort_field="data_invio",
        filter_param=None,  # niente filtro: data libera senza dropdown
        filter_kind=None,
        css_th="px-3 py-1 w-28",
        css_td="px-3 tabular-nums text-xs",
    ),
    "protocollo_invio": ColumnSpec(
        code="protocollo_invio",
        label="N° Fornitura",
        label_short="N° Forn.",
        sort_field="protocollo_invio",
        filter_param="f_protocollo",
        filter_kind="text",
        css_th="px-3 py-1 w-28",
        css_td="px-3 font-mono text-xs",
    ),
    "note": ColumnSpec(
        code="note",
        label="Note periodo",
        label_short="Note",
        sort_field=None,
        filter_param="f_note",
        filter_kind="text",
        css_th="px-3 py-1 w-32",
        css_td="px-3 text-xs",
    ),
}


# Set di default usato quando per un tipo adempimento non e' definita
# una configurazione `VistaAdempimentoColonne`. Ordine = ordine in tabella.
# Le viste aggregate (es. anno LIPE) escluderanno automaticamente le colonne
# per-periodo (`stato`, `note`, `data_invio`, `protocollo_invio`).
DEFAULT_COLUMN_CODES: list[str] = [
    "codice_multi",
    "cliente",
    "tipo_soggetto",
    "tipo_contabilita",
    "regime_contabile",
    "periodicita_iva",
    "referente_contab",
    "referente_consul",
    "stato",
    "data_invio",
    "protocollo_invio",
    "note",
]


# Colonne che hanno senso solo nelle viste "singolo periodo": sono attributi
# del record `Adempimento` (non dell'anagrafica) e nelle viste aggregate
# (es. LIPE-anno con 4 celle Q1..Q4) verrebbero ambigue.
PER_PERIOD_CODES: frozenset[str] = frozenset({
    "stato", "note", "data_invio", "protocollo_invio",
})


def resolve_columns(
    codes: Iterable[str],
    *,
    exclude_per_period: bool = False,
) -> list[ColumnSpec]:
    """Risolve una lista di codici colonna in lista di `ColumnSpec`.

    - Salta codici sconosciuti (non solleva: tollerante a config malformate).
    - Se `exclude_per_period=True`, scarta le colonne in `PER_PERIOD_CODES`
      (uso tipico: viste aggregate come LIPE-anno).
    """
    out: list[ColumnSpec] = []
    for code in codes:
        if exclude_per_period and code in PER_PERIOD_CODES:
            continue
        spec = STANDARD_COLUMNS.get(code)
        if spec is not None:
            out.append(spec)
    return out


def get_columns_for_tipo(
    tipo,
    *,
    vista: str = "singolo",
    exclude_per_period: bool = False,
) -> list[ColumnSpec]:
    """Restituisce le colonne configurate per un `TipoAdempimentoCatalogo`.

    Cerca una `VistaAdempimentoColonne` (tipo, vista). Se non esiste,
    ricade su `DEFAULT_COLUMN_CODES`.

    `vista` puo' essere 'singolo' (vista per-periodo) o 'anno' (aggregata).
    """
    columns, _ = get_view_config_for_tipo(
        tipo, vista=vista, exclude_per_period=exclude_per_period,
    )
    return columns


def get_view_config_for_tipo(
    tipo,
    *,
    vista: str = "singolo",
    exclude_per_period: bool = False,
) -> tuple[list[ColumnSpec], dict[str, int]]:
    """Risolve (colonne, larghezze) per (tipo, vista).

    Ritorna sempre una tupla; le larghezze sono un dict `{codice: px}` con
    solo i codici per cui esiste un override (le altre useranno le classi
    Tailwind di default da `ColumnSpec.css_th`).
    """
    from .models import VistaAdempimentoColonne

    codes: list[str] = list(DEFAULT_COLUMN_CODES)
    widths: dict[str, int] = {}
    if tipo is not None:
        config = (
            VistaAdempimentoColonne.objects
            .filter(tipo=tipo, vista=vista)
            .first()
        )
        if config:
            if config.colonne_codici:
                codes = list(config.colonne_codici)
            raw = config.larghezze_colonne or {}
            # Sanifica: solo codici noti, valori interi ragionevoli (40..800).
            for code, val in raw.items():
                if code not in STANDARD_COLUMNS:
                    continue
                try:
                    px = int(val)
                except (TypeError, ValueError):
                    continue
                if 40 <= px <= 800:
                    widths[code] = px

    return resolve_columns(codes, exclude_per_period=exclude_per_period), widths


def available_column_choices() -> list[tuple[str, str]]:
    """Ritorna [(code, label), ...] per popolare il widget admin."""
    return [(spec.code, spec.label) for spec in STANDARD_COLUMNS.values()]
