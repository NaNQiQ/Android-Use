"""App-independent accessibility coverage and visible geometry helpers."""
import hashlib
import json
import re


def visible_rect(bounds, viewport):
    if isinstance(bounds, str):
        parts = [int(x) for x in re.findall(r'-?\d+', bounds)]
    elif isinstance(bounds, dict):
        parts = [bounds.get(k, 0) for k in ('left', 'top', 'right', 'bottom')]
    else:
        return None
    if len(parts) != 4:
        return None
    left, top, right, bottom = parts
    left, top = max(0, left), max(0, top)
    right, bottom = min(viewport['width'], right), min(viewport['height'], bottom)
    return (left, top, right, bottom) if right > left and bottom > top else None


def app_nodes(nodes, package):
    result = []
    for node in nodes:
        owner = node.get('package')
        rid = node.get('resource-id', '')
        if owner and package and owner != package:
            continue
        if not owner and rid.startswith(('com.android.systemui:', 'com.sohu.inputmethod.', 'androidhnext:')):
            continue
        result.append(node)
    return result


def assess(nodes, app, viewport, truncated=False):
    own = app_nodes(nodes, app.get('package'))
    visible = [n for n in own if visible_rect(n.get('bounds'), viewport)]
    labeled = [n for n in visible if n.get('text') or n.get('content-desc')]
    body = [n for n in labeled if visible_rect(n['bounds'], viewport)[1] >= viewport['height'] * .22
            and visible_rect(n['bounds'], viewport)[1] < viewport['height'] * .90]
    custom = any('WebView' in n.get('class', '') or 'SurfaceView' in n.get('class', '')
                 or 'TextureView' in n.get('class', '') for n in visible)
    if not labeled:
        status, reason = 'unavailable', 'No visible app labels; page may be empty or custom-drawn'
    elif truncated or len(body) < 3 or (custom and len(body) < 6):
        status, reason = 'limited', 'Sparse body labels, custom surface or truncated hierarchy'
    else:
        status, reason = 'usable', 'Visible app labels available; unexposed visual content may still be missing'
    return {'status': status, 'reason': reason, 'app_nodes': len(own),
            'visible_labels': len(labeled), 'body_labels': len(body),
            'complete': False, 'assessment': 'heuristic', 'screenshot_recommended': status != 'usable'}


def page_signature(nodes, app, viewport):
    # Exclude system clock/keyboard churn, but include app content and interactive state.
    rows = [{k: n[k] for k in ('resource-id', 'class', 'bounds', 'text', 'content-desc',
                              'enabled', 'selected', 'checked', 'clickable', 'scrollable') if k in n}
            for n in app_nodes(nodes, app.get('package')) if visible_rect(n.get('bounds'), viewport)]
    value = [app.get('package'), app.get('activity'), viewport, rows]
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
