from django import template

register = template.Library()


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
