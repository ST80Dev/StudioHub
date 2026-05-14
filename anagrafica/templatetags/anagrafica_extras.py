from django import template

register = template.Library()


# Abbreviazioni compatte per la colonna "Contabilità" nelle liste degli
# adempimenti. Le label canoniche ("Interna (tenuta dallo studio)" /
# "Esterna") sono troppo lunghe per le celle di una tabella densa: nelle
# liste mostriamo "INT" / "EST". Centralizzato qui per essere usato da
# tutte le tabelle adempimenti (vedi CLAUDE.md).
_CONTAB_ABBR = {"interna": "INT", "esterna": "EST"}


@register.filter
def contab_abbr(value):
    """Abbrevia un codice GestioneContabilita in 'INT' / 'EST'.

    Accetta sia il codice raw (`'interna'`) sia l'istanza Anagrafica
    (legge `value.contabilita`). Fallback al codice stesso se non
    riconosciuto, "—" se vuoto.
    """
    if value is None or value == "":
        return "—"
    code = getattr(value, "contabilita", value)
    return _CONTAB_ABBR.get(code, code or "—")


@register.filter
def get_attr(obj, name: str):
    """Accesso dinamico a un attributo: `{{ obj|get_attr:'codice_fiscale' }}`.

    Per i dict supporta lookup per chiave variabile (sia stringa che int):
    `{{ d|get_attr:q }}` ritorna `d[q]` se presente, altrimenti `d[int(q)]`
    se la chiave esiste in forma numerica. Necessario per template che
    iterano su una stringa di indici (es. {% for q in "1234" %}) e cercano
    nel dict una chiave int.
    """
    if obj is None:
        return ""
    try:
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
            try:
                ikey = int(name)
            except (TypeError, ValueError):
                return ""
            return obj.get(ikey, "")
        return getattr(obj, name, "")
    except Exception:
        return ""
