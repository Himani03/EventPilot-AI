from urllib.parse import urlencode
from src.db import record_click

def make_tracked_url(base_url, event_id, variant_id):
    base_url = (base_url or "http://localhost:8501").rstrip("/")
    return f"{base_url}/?{urlencode({'track_event': event_id, 'track_variant': variant_id})}"

def record_query_click(params):
    """Record a click once per URL visit; app.py removes tracking params after processing."""
    try:
        event_id = int(params.get("track_event", 0))
        variant_id = int(params.get("track_variant", 0))
        if event_id > 0 and variant_id > 0:
            record_click(variant_id, event_id)
            return True
    except (TypeError, ValueError):
        pass
    return False
