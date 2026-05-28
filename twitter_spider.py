from base_spider import BaseSpider


class TwitterSpider(BaseSpider):
    """Twitter-specific spider that intercepts GraphQL API responses to extract video URLs."""

    DEFAULT_REFERER = "https://x.com/"

    def handle_response(self, response):
        """Intercept Twitter GraphQL API responses to extract video variants."""
        try:
            # Only process GraphQL API calls
            if '/i/api/graphql/' not in response.url:
                return
            if response.status != 200:
                return

            body = response.json()
            variants = self._find_variants(body)
            if variants:
                for v in variants:
                    if v.get('content_type') == 'video/mp4':
                        bitrate = v.get('bitrate', 0)
                        url = v.get('url', '')
                        if url and bitrate > 0:
                            self.video_candidates.append({
                                'url': url,
                                'size': bitrate  # use bitrate for sorting
                            })
        except Exception:
            pass

    def _find_variants(self, obj):
        """Recursively search for video variants in nested dict/list structure."""
        if isinstance(obj, dict):
            if 'variants' in obj and isinstance(obj['variants'], list):
                # Check if this variants list contains video/mp4 entries
                for v in obj['variants']:
                    if isinstance(v, dict) and v.get('content_type') == 'video/mp4':
                        return obj['variants']
            # Recursively search nested values
            for v in obj.values():
                result = self._find_variants(v)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._find_variants(item)
                if result:
                    return result
        return None

    def extract_title(self, page):
        """Extract tweet title from og:title meta tag, falling back to page title."""
        try:
            og_title = page.locator('meta[property="og:title"]').get_attribute('content')
            if og_title:
                return og_title.strip()
        except Exception:
            pass
        return page.title() or ""
