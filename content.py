"""Extract readable source text, keeping feed excerpts distinct from article bodies."""
from html.parser import HTMLParser
import re
import ipaddress
import socket
from urllib.parse import urlsplit
import urllib.request


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.hidden += 1
        if tag in ('p', 'div', 'br', 'h1', 'h2', 'h3', 'li') and not self.hidden:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(html):
    parser = TextExtractor()
    parser.feed(html)
    return re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()


def require_public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid public URL')
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
        raise ValueError('Non-public URL not allowed')


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def evidence(item):
    fallback = plain_text(item.get('content', ''))
    result = dict(text=fallback, kind='feed_content', retrieval_error=None)
    try:
        request = urllib.request.Request(item['url'], headers={'User-Agent': 'AINewsMVP/0.1'})
        if item.get('source') == 'hacker_news':
            require_public_url(item['url'])
            opener = urllib.request.build_opener(PublicRedirect())
            response_context = opener.open(request, timeout=25)
        else:
            response_context = urllib.request.urlopen(request, timeout=25)
        with response_context as response:
            if 'html' not in response.headers.get('Content-Type', ''):
                raise ValueError('Article response is not HTML')
            raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ValueError('Article exceeds size limit')
            html = raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
        # Use a bounded article/main region rather than navigation and footer text.
        for tag in ('article', 'main'):
            match = re.search(r'<'+tag+r'\b[^>]*>(.*?)</'+tag+r'>', html, re.I | re.S)
            if match:
                text = plain_text(match.group(1))
                if len(text) > len(fallback):
                    result.update(text=text, kind='article_body')
                break
    except Exception as exc:
        result['retrieval_error'] = str(exc)
    result['truncated'] = len(result['text']) > 50000
    result['text'] = result['text'][:50000]
    return result
