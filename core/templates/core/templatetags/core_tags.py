# core/templatetags/core_tags.py

from django import template
from django.template.defaultfilters import stringfilter
import markdown as md

register = template.Library() # KYA YEH LINE BILKUL AISI HAI?

@register.filter()
@stringfilter
def markdown(value):
    # Ensure 'pip install markdown' is done
    return md.markdown(value, extensions=['markdown.extensions.fenced_code'])