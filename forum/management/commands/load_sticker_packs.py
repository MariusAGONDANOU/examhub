from django.core.management.base import BaseCommand
from django.conf import settings
import os, json, requests

CATEGORIES = [
    ('gif', 'trending'),
    ('gif', 'reactions'),
    ('sticker', 'stickers'),
]

def _tenor(endpoint, params):
    key = getattr(settings, 'TENOR_API_KEY', None) or 'LIVDSRZULELA'
    url = f'https://tenor.googleapis.com/v2/{endpoint}'
    params = dict(params or {})
    params['key'] = key
    r = requests.get(url, params=params, timeout=12)
    r.raise_for_status()
    return r.json()

class Command(BaseCommand):
    help = "Précharge quelques lots GIF/Stickers depuis Tenor dans un cache JSON (aucune DB)."

    def handle(self, *args, **opts):
        base_dir = getattr(settings, 'BASE_DIR', os.getcwd())
        cache_dir = os.path.abspath(os.path.join(base_dir, 'protected_media'))
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, 'forum_assets_cache.json')

        cache = {}
        for kind, q in CATEGORIES:
            self.stdout.write(f'Fetching {kind}:{q} ...')
            params = {'q': q, 'limit': 50}
            if kind == 'sticker':
                params['media_filter'] = 'tinygif,webp'
                params['type'] = 'sticker'
            else:
                params['media_filter'] = 'gif'
            data = _tenor('search', params)
            results = data.get('results') or data.get('gifs') or []
            items = []
            for it in results:
                media = it.get('media_formats') or {}
                candidate = media.get('gif') or media.get('mediumgif') or media.get('tinygif') or media.get('webp') or media.get('nanogif') or {}
                url = candidate.get('url') or it.get('url') or ''
                if url:
                    items.append({'url': url, 'kind': kind})
            cache[f'{kind}:{q}'] = items

        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        self.stdout.write(self.style.SUCCESS(f'Cache écrit: {cache_path}'))