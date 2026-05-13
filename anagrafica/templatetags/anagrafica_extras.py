from django import template

register = template.Library()


@register.filter
def get_attr(obj, name: str):
    """Accesso dinamico a un attributo: `{{ obj|get_attr:'codice_fiscale' }}`."""
    if obj is None:
        return ""
    try:
        return getattr(obj, name, "")
    except Exception:
        return ""
