"""Formatting rules shared by generation and Telegram delivery."""
import re

PERSIAN_INITIAL = re.compile(r'^[آاأإبپتثجچحخدذرزژسشصضطظعغفقکكگلمنوهیيئؤةۀ]')


def remove_source_footer(body, source_url):
    """Remove a model-generated trailing source line; the publisher adds it once."""
    paragraphs = re.split(r'\n\s*\n', body.strip())
    while paragraphs:
        last = paragraphs[-1].strip()
        if '\n' not in last and re.match(r'^(?:منبع|source)\s*[:：]', last, re.I) and source_url in last:
            paragraphs.pop()
        else:
            break
    return '\n\n'.join(paragraphs)


def validate_post(body):
    paragraphs = re.split(r'\n\s*\n', body.strip())
    if not body.strip() or len(body) > 3500:
        raise ValueError('Draft must be nonempty and fit a Telegram message')
    for index, paragraph in enumerate(paragraphs, 1):
        if not PERSIAN_INITIAL.match(paragraph.lstrip()):
            raise ValueError(f'Paragraph {index} must start with a Persian word for RTL display')
