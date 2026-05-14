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


@register.filter
def referente_principale_attivo(cliente, ruolo: str):
    """Wrapper template per `Anagrafica.referente_principale_attivo(ruolo)`.

    Usato dalle celle della lista per ottenere il referente da mostrare.
    Esegue una query per riga (N+1 sulla pagina paginata: accettabile a
    50 record/pagina; ottimizzabile in futuro con prefetch).
    """
    if cliente is None:
        return None
    try:
        return cliente.referente_principale_attivo(ruolo)
    except Exception:
        return None
