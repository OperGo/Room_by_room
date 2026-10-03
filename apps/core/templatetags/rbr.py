from django import template
from django.utils.html import format_html

from apps.core.money import format_gbp

register = template.Library()


@register.filter
def gbp(value):
    return format_gbp(value)


@register.filter
def gbp_signed(value):
    return format_gbp(value, signed=True)


@register.simple_tag
def icon(name, size=20, label=""):
    if label:
        return format_html(
            '<svg class="icon" width="{0}" height="{0}" role="img" aria-label="{2}"><use href="#i-{1}"></use></svg>',
            size, name, label,
        )
    return format_html(
        '<svg class="icon" width="{0}" height="{0}" aria-hidden="true" focusable="false"><use href="#i-{1}"></use></svg>',
        size, name,
    )


@register.filter
def minutes(value):
    if not value:
        return ""
    hours, mins = divmod(int(value), 60)
    if hours and mins:
        return f"{hours} h {mins} min"
    if hours:
        return f"{hours} h"
    return f"{mins} min"


@register.filter
def length_is_one(value):
    try:
        return len(value) == 1
    except TypeError:
        return False


@register.filter
def action_label(value):
    return str(value).replace("_", " ").capitalize()
