"""Metadati sui campi del profilo cliente usati dal motore regole.

Questo modulo è la sorgente unica di verità su:
- quali campi di Anagrafica sono valutabili da una regola;
- che tipo hanno (enum chiuso · booleano · testo libero);
- quali sono i valori validi (per gli enum).

I form di configurazione, la validazione lato server e la pagina matrice
profili → adempimenti leggono tutti da qui per restare allineati.
"""
from anagrafica.models import (
    GestioneContabilita,
    PeriodicitaIVA,
    RegimeContabile,
    TipoSoggetto,
)


KIND_ENUM = "enum"
KIND_BOOL = "bool"
KIND_TEXT = "text"


CAMPI_INFO = {
    "tipo_soggetto": {
        "label": "Tipo soggetto",
        "kind": KIND_ENUM,
        "choices": list(TipoSoggetto.choices),
    },
    "regime_contabile": {
        "label": "Regime contabile",
        "kind": KIND_ENUM,
        "choices": list(RegimeContabile.choices),
    },
    "periodicita_iva": {
        "label": "Periodicità IVA",
        "kind": KIND_ENUM,
        "choices": list(PeriodicitaIVA.choices),
    },
    "contabilita": {
        "label": "Contabilità (interna/esterna)",
        "kind": KIND_ENUM,
        "choices": list(GestioneContabilita.choices),
    },
    "sostituto_imposta": {
        "label": "Sostituto d'imposta",
        "kind": KIND_BOOL,
        "choices": [],
    },
    "iscritto_cciaa": {
        "label": "Iscritto CCIAA",
        "kind": KIND_BOOL,
        "choices": [],
    },
    "categoria_professione": {
        "label": "Categoria professione",
        "kind": KIND_TEXT,
        "choices": [],
    },
}


def kind_di(campo: str) -> str:
    """Ritorna il kind ('enum'/'bool'/'text') del campo, o '' se ignoto."""
    info = CAMPI_INFO.get(campo)
    return info["kind"] if info else ""


def valori_validi(campo: str) -> set[str]:
    """Insieme dei valori accettati per un campo enum. Vuoto per altri kind."""
    info = CAMPI_INFO.get(campo)
    if not info or info["kind"] != KIND_ENUM:
        return set()
    return {val for val, _ in info["choices"]}


# ---------------------------------------------------------------------------
# Casistiche tipiche per la pagina "Matrice profili → adempimenti"
# ---------------------------------------------------------------------------
#
# Ogni casistica è un cliente fittizio con un profilo fiscale plausibile.
# La pagina matrice esegue il motore regole su ciascuna e mostra quali tipi
# adempimento risultano applicabili. Serve sia come debug delle regole
# configurate che come documentazione operativa.
#
# Aggiungere/modificare casistiche qui non richiede migrazioni: è semplice
# codice Python. Se in futuro vorremo renderle editabili da UI, le sposteremo
# in una tabella DB.

CASISTICHE_TIPICHE = [
    {
        "nome": "SRL ordinaria · IVA mensile · CCIAA · Sostituto",
        "profilo": dict(
            tipo_soggetto="SRL",
            regime_contabile="ordinario",
            periodicita_iva="mensile",
            contabilita="esterna",
            sostituto_imposta=True,
            iscritto_cciaa=True,
            categoria_professione="",
        ),
    },
    {
        "nome": "SRL ordinaria · IVA trimestrale · CCIAA · Sostituto",
        "profilo": dict(
            tipo_soggetto="SRL",
            regime_contabile="ordinario",
            periodicita_iva="trimestrale",
            contabilita="esterna",
            sostituto_imposta=True,
            iscritto_cciaa=True,
            categoria_professione="",
        ),
    },
    {
        "nome": "SPA · IVA mensile · CCIAA · Sostituto",
        "profilo": dict(
            tipo_soggetto="SPA",
            regime_contabile="ordinario",
            periodicita_iva="mensile",
            contabilita="esterna",
            sostituto_imposta=True,
            iscritto_cciaa=True,
            categoria_professione="",
        ),
    },
    {
        "nome": "SAS · IVA trimestrale · CCIAA",
        "profilo": dict(
            tipo_soggetto="SAS",
            regime_contabile="ordinario",
            periodicita_iva="trimestrale",
            contabilita="esterna",
            sostituto_imposta=False,
            iscritto_cciaa=True,
            categoria_professione="",
        ),
    },
    {
        "nome": "SNC · IVA trimestrale · CCIAA",
        "profilo": dict(
            tipo_soggetto="SNC",
            regime_contabile="ordinario",
            periodicita_iva="trimestrale",
            contabilita="esterna",
            sostituto_imposta=False,
            iscritto_cciaa=True,
            categoria_professione="",
        ),
    },
    {
        "nome": "DI ordinaria · IVA trimestrale · CCIAA",
        "profilo": dict(
            tipo_soggetto="DI",
            regime_contabile="ordinario",
            periodicita_iva="trimestrale",
            contabilita="esterna",
            sostituto_imposta=False,
            iscritto_cciaa=True,
            categoria_professione="",
        ),
    },
    {
        "nome": "DI semplificata · IVA trimestrale · CCIAA",
        "profilo": dict(
            tipo_soggetto="DI",
            regime_contabile="semplificato",
            periodicita_iva="trimestrale",
            contabilita="esterna",
            sostituto_imposta=False,
            iscritto_cciaa=True,
            categoria_professione="",
        ),
    },
    {
        "nome": "DI forfettaria · No IVA · CCIAA",
        "profilo": dict(
            tipo_soggetto="DI",
            regime_contabile="forfettario",
            periodicita_iva="non_soggetto",
            contabilita="esterna",
            sostituto_imposta=False,
            iscritto_cciaa=True,
            categoria_professione="",
        ),
    },
    {
        "nome": "Professionista ordinario · IVA trimestrale",
        "profilo": dict(
            tipo_soggetto="PROFEX",
            regime_contabile="ordinario",
            periodicita_iva="trimestrale",
            contabilita="esterna",
            sostituto_imposta=False,
            iscritto_cciaa=False,
            categoria_professione="",
        ),
    },
    {
        "nome": "Professionista forfettario · No IVA",
        "profilo": dict(
            tipo_soggetto="PROFEX",
            regime_contabile="forfettario",
            periodicita_iva="non_soggetto",
            contabilita="esterna",
            sostituto_imposta=False,
            iscritto_cciaa=False,
            categoria_professione="",
        ),
    },
    {
        "nome": "Professionista sanitario · IVA trimestrale",
        "profilo": dict(
            tipo_soggetto="PROFEX",
            regime_contabile="ordinario",
            periodicita_iva="trimestrale",
            contabilita="esterna",
            sostituto_imposta=False,
            iscritto_cciaa=False,
            categoria_professione="sanitaria",
        ),
    },
    {
        "nome": "Persona fisica privata · No IVA",
        "profilo": dict(
            tipo_soggetto="PF",
            regime_contabile="non_applicabile",
            periodicita_iva="non_soggetto",
            contabilita="esterna",
            sostituto_imposta=False,
            iscritto_cciaa=False,
            categoria_professione="",
        ),
    },
    {
        "nome": "Associazione · IVA trimestrale · No CCIAA",
        "profilo": dict(
            tipo_soggetto="ASS",
            regime_contabile="ordinario",
            periodicita_iva="trimestrale",
            contabilita="esterna",
            sostituto_imposta=False,
            iscritto_cciaa=False,
            categoria_professione="",
        ),
    },
]
