from django import template

register = template.Library()


@register.filter
def get_item(value, key):
    """Accesso a dict con chiave dinamica nel template: `{{ d|get_item:k }}`."""
    if value is None:
        return ""
    try:
        return value.get(key, "")
    except AttributeError:
        return ""
