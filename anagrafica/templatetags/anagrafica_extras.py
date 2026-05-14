from django import template

from anagrafica import choices_labels

register = template.Library()


@register.filter
def micro_label(codice, field):
    """Sigla 3 char per un codice (es. 'INT' per 'interna').

    Uso nei template: `{{ c.contabilita|micro_label:'contabilita' }}`.
    Legge `TextChoiceLabel.label_micro` (configurabile da admin) con
    fallback automatico dalle prime 3 lettere della label estesa. Vedi
    `anagrafica.choices_labels.get_micro_label`.

    Convenzione "3 livelli di etichetta": codice DB (`interna`) → micro
    (`INT`, celle dense) → label estesa (`Interna (tenuta dallo studio)`,
    form e dropdown). Vedi CLAUDE.md.
    """
    if codice is None or codice == "":
        return "—"
    return choices_labels.get_micro_label(field, codice) or "—"


@register.filter
def label_for(codice, field):
    """Label estesa override-aware per un codice.

    Uso: `{{ c.stato|label_for:'stato' }}`. Equivalente a
    `c.get_stato_display()` ma usabile da template generici che ricevono
    il field name come parametro.
    """
    if codice is None or codice == "":
        return ""
    return choices_labels.get_label(field, codice)


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
