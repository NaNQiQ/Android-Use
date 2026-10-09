"""Windows/Android MCP adapter. Tool/preview contract adapted from iPhone Use (MIT)."""
import argparse
import base64
import collections
import hashlib
import io
import json
import math
import os
import queue
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

import adbutils
import jsonschema
import uiautomator2 as u2

sys.path.insert(0, str(Path(__file__).resolve().parent))
from android_lock import DeviceLock
from android_stream import ScreenStream
from android_observation import assess, visible_rect, page_signature, app_nodes

ROOT = Path(__file__).resolve().parents[1]
URI = "ui://android-use/phone-v0.2.3.html"
VERSION = '0.2.3'
UI_META = {"ui": {"resourceUri": URI}, "openai/outputTemplate": URI}
RESOURCE_META = {"ui": {"csp": {"connectDomains": [], "resourceDomains": []}, "prefersBorder": False},
                 "openai/ui": {"availableDisplayModes": ["fullscreen"], "preferredDisplayMode": "fullscreen"}}

def obj(p=None, required=()):
    return {"type": "object", "properties": p or {}, "required": list(required), "additionalProperties": False}

STR = {"type": "string", "minLength": 1, "maxLength": 10000}
NUM = {"type": "number", "minimum": 0, "maximum": 10000}
SELECTOR = obj({k: STR for k in ("text", "textContains", "resourceId", "description", "className")})
SELECTOR["minProperties"] = 1
SCHEMAS = {
    "doctor": obj(), "ready": obj(),
    "observe": obj({"mode": {"enum": ["auto", "tree", "screenshot", "both"]}}),
    "find": obj({"selector": SELECTOR}, ("selector",)),
    "tap": obj({"selector": SELECTOR, "x": NUM, "y": NUM}),
    "swipe": obj({"x1": NUM, "y1": NUM, "x2": NUM, "y2": NUM,
                  "duration": {"type": "number", "minimum": .1, "maximum": 2}}, ("x1", "y1", "x2", "y2")),
    "type_text": obj({"selector": SELECTOR, "text": {"type":"string", "maxLength":10000}}, ("selector", "text")),
    "press_button": obj({"name": {"enum": ["home", "back", "recent"]}}, ("name",)),
    "launch_app": obj({"package": STR}, ("package",)),
    "wait": obj({"selector": SELECTOR, "timeout": {"type": "number", "minimum": 0, "maximum": 20}}, ("selector",)),
    "screen": obj({"action": {"enum": ["open", "pause", "resume"]}}),
    "screen_frame": obj({"after_seq": NUM, "last_event_id": NUM}),
    "screen_action": obj({"action": {"enum": ["refresh", "home", "screenshot"]}}, ("action",)),
    "setup": obj({"action": {"enum": ["discover", "status", "reconnect"]}, "serial": STR}, ("action",)),
    "apps": obj({"query": {"type":"string", "maxLength":100}, "limit": {"type":"integer", "minimum":1, "maximum":100}}),
    "scroll_find": obj({"selector":SELECTOR, "direction":{"enum":["up","down"]}}, ("selector",)),
    "collect_list": obj({"max_pages":{"type":"integer","minimum":1,"maximum":6},
                         "className":STR, "end_selector":SELECTOR}),
}
MUTATIONS = ('tap','swipe','type_text','press_button','launch_app')
for name in MUTATIONS:
    SCHEMAS[name]['properties']['expect'] = SELECTOR
    SCHEMAS[name]['properties']['mode'] = {'enum': ['auto', 'tree', 'screenshot', 'both']}
    SCHEMAS[name]['properties']['verify'] = obj({
        'selector': SELECTOR, 'absent': SELECTOR, 'toastContains': STR,
        'package': STR, 'activity': STR,
        'timeout': {'type': 'number', 'minimum': 0, 'maximum': 5}})
    SCHEMAS[name]['properties']['verify']['anyOf'] = [
        {'required': [key]} for key in ('selector', 'absent', 'toastContains', 'package', 'activity')]
for name in ('tap','swipe'):
    SCHEMAS[name]['properties']['observation_id'] = STR
SCHEMAS['batch'] = obj({'steps':{'type':'array','minItems':1,'maxItems':12,'items':{'oneOf':[
    obj({'op':{'const':n}, 'args':SCHEMAS[n]},('op','args'))
    for n in (*MUTATIONS,'wait','observe')
]}}},('steps',))
# Sequence numbers are counters rather than coordinates.
SCHEMAS["screen_frame"]["properties"]["after_seq"] = {"type": "integer", "minimum": 0}
SCHEMAS["screen_frame"]["properties"]["last_event_id"] = {"type": "integer", "minimum": 0}
DESCRIPTIONS = {
    "doctor": "List USB Android devices and dependencies without reading phone content.",
    "ready": "Connect the selected Android device and verify automation readiness.",
    "observe": "Auto returns app tree plus a fresh screenshot when coverage is limited. Coverage is heuristic, not proof of completeness.",
    "find": "Find controls using exact Android selector fields.",
    "tap": "Tap one available visible selector OR x/y with observation_id. Auto returns tree/screenshot and verification status. expect/verify checks postconditions, not business success.",
    "swipe": "Swipe viewport pixels with observation_id; duration is seconds (0.1-2). Auto returns tree/screenshot and verification. Never blindly repeat.",
    "type_text": "Replace one editable field with Unicode text, verify readback; never submit.",
    "press_button": "Press Android home/back/recent once and observe.",
    "launch_app": "Open an installed Android package and observe.",
    "wait": "Wait a bounded time for a selector.",
    "screen": "Open, pause or resume the Android preview sidebar. Uses scrcpy video with cached-frame transport and snapshot fallback.",
    "screen_frame": "Preview frame for the screen widget.",
    "screen_action": "Preview toolbar action. Screenshot refreshes preview only.",
    "setup": "Discover, inspect or reconnect the phone service without replaying an action.",
    "apps": "List installed package IDs matching an optional query.",
    "scroll_find": "Look for a selector, swipe once if needed, then return matches or screenshot for inspection.",
    "collect_list": "Read bounded visible text rows, scroll with deduplication and report actual coverage.",
    "batch": "Execute known steps sequentially; stop on the first error or failed expectation.",
}
TOOLS = [{"name": "android_" + n, "description": DESCRIPTIONS[n], "inputSchema": s,
          **({"_meta": {"ui": {"resourceUri": URI, "visibility": ["app"]}}} if n in ("screen_frame", "screen_action")
             else {"_meta": UI_META} if n in ("screen","ready") else {})}
         for n, s in SCHEMAS.items()]

class Runtime:
    def __init__(self, serial=None):
        self.serial = serial
        self.d = None
        self.paused = False
        self.seq = 0
        self.device_lock = None
        self.stream = None
        self.busy = False
        self.events = collections.deque(maxlen=30)
        self.event_seq = 0
        self.observation = None
        self.observations = collections.OrderedDict()
        self.health = {'locked': True, 'online': False}
        self.health_stop = threading.Event()
        self.health_thread = None
        self.read_lock = threading.RLock()
        self.preview_viewport = None

    def connect(self):
        devices = adbutils.adb.device_list()
        if not self.serial:
            if len(devices) != 1:
                raise ValueError("Choose --serial explicitly when zero or multiple authorized devices are present")
            self.serial = devices[0].serial
        if self.serial not in [device.serial for device in devices]:
            self.d = None
            raise ConnectionError('Selected Android device is disconnected or unauthorized; reconnect USB and call setup')
        if self.d is None:
            self.d = u2.connect(self.serial)
            self.d.settings['wait_timeout'] = 3
            self.device_lock = DeviceLock(self.serial)
        return self.d

    def locked(self):
        self.connect()
        return self.check_health()

    def check_health(self):
        device=adbutils.adb.device(self.serial)
        policy=device.shell(['dumpsys','window','policy'],timeout=3)
        power=device.shell(['dumpsys','power'],timeout=3)
        locked = any(re.search(r'\b'+key+r'\s*=\s*true',policy) for key in
                     ('mShowingLockscreen','mKeyguardShowing','mInputRestricted','showing','isStatusBarKeyguard'))
        wake=re.search(r'\bmWakefulness=(\w+)',power)
        locked = locked or (wake is None or wake.group(1)!='Awake')
        self.health = {'locked':locked,'online':True}
        return locked

    def monitor(self):
        def watch():
            while not self.health_stop.wait(1):
                try: self.check_health()
                except Exception: self.health = {'locked':True,'online':False}
                if self.health['locked'] and self.stream: self.stream.stop()
                if self.health['online'] and not self.busy:
                    try: self.preview_viewport = dict(zip(('width','height'),adbutils.adb.device(self.serial).window_size()))
                    except Exception: pass
        if not self.health_thread:
            self.health_thread = threading.Thread(target=watch,daemon=True,name='android-health')
            self.health_thread.start()

    def close(self):
        self.health_stop.set()
        if self.stream: self.stream.stop()
        if self.health_thread: self.health_thread.join(timeout=4)

    def tree(self, remember=True):
        d = self.connect()
        nodes = []
        for e in ET.fromstring(d.dump_hierarchy()).iter("node"):
            a = e.attrib
            if not any(a.get(k) for k in ("text", "content-desc", "resource-id")) and a.get("clickable") != "true":
                continue
            node = {k: a[k] for k in ("text", "content-desc", "resource-id", "class", "bounds", "clickable", "enabled", "password", "package", "selected", "checked", "focused", "scrollable") if a.get(k)}
            if a.get('password') == 'true':
                node.pop('text',None); node.pop('content-desc',None)
            nodes.append(node)
        viewport = dict(zip(("width", "height"), d.window_size()))
        self.preview_viewport = viewport
        app = self.foreground()
        # App nodes precede chrome so system/keyboard nodes cannot crowd out the page.
        own = app_nodes(nodes, app.get('package'))
        own_ids = {id(n) for n in own}
        nodes = own + [n for n in nodes if id(n) not in own_ids]
        observation = {"app": app, "viewport": viewport, "nodes": nodes[:250],
                       "truncated": len(nodes) > 250}
        observation['tree_quality'] = assess(nodes, app, viewport, observation['truncated'])
        if remember:
            self.remember(observation)
        return observation

    def remember(self, observation):
        ident = uuid.uuid4().hex
        observation['observation_id'] = ident
        context = {'at': time.monotonic(), 'app': observation['app'], 'viewport': observation['viewport'],
                   'signature': page_signature(observation.get('nodes', []), observation['app'], observation['viewport'])
                   if 'nodes' in observation else None}
        self.observations[ident] = context
        while len(self.observations) > 16:
            self.observations.popitem(last=False)
        self.observation = (ident, context['viewport'], context['app'].get('package'), context['at'])

    def capture(self, mode='auto', observation=None):
        observation = observation or self.tree(remember=False)
        quality = observation.get('tree_quality', {})
        needs_image = mode in ('both', 'screenshot') or (mode == 'auto' and quality.get('screenshot_recommended', True))
        picture = None
        if needs_image:
            if self.locked():
                raise ValueError('Unlock phone before capturing')
            picture = self.image()  # Fresh phone capture, never a pre-action preview cache.
            observation['image_captured_at'] = time.time() * 1000
            if observation['viewport'] != dict(zip(('width', 'height'), self.connect().window_size())) or observation['app'] != self.foreground():
                raise ValueError('Page context changed during screenshot; observe again')
        self.remember(observation)
        observation['returned_mode'] = 'both' if picture else 'tree'
        if mode == 'screenshot':
            observation.pop('nodes', None)
            observation['returned_mode'] = 'screenshot'
        return {'observation': observation, 'image': picture}

    def image(self):
        im = self.connect().screenshot()
        b = io.BytesIO()
        im.save(b, format="PNG")
        return {"type": "image", "mimeType": "image/png", "data": base64.b64encode(b.getvalue()).decode()}

    def validate_observation(self, observation_id):
        context = self.observations.get(observation_id)
        if not context:
            raise ValueError('Unknown observation_id; observe the screen again')
        if time.monotonic()-context['at'] > 30 or context['viewport'] != dict(zip(('width','height'),self.connect().window_size())) or context['app'] != self.foreground():
            raise ValueError('Observation is stale or viewport/app changed; observe again')
        if context['signature']:
            current = self.tree(remember=False)
            if context['signature'] != page_signature(current['nodes'], current['app'], current['viewport']):
                raise ValueError('Visible app hierarchy changed since observation; observe again')

    def foreground(self):
        d=self.connect()
        if not hasattr(d,'serial'):return d.app_current()
        output=adbutils.adb.device(self.serial).shell(['dumpsys','activity','activities'],timeout=3)
        # Android 16/Honor uses topResumedActivity; upstream app_current can pick a background app.
        match=re.search(r'(?:topResumedActivity=|mResumedActivity:\s*)ActivityRecord\{[^\n]*?\s([\w.]+)/([^\s}]+)',output)
        if match:return {'package':match.group(1),'activity':match.group(2)}
        return {'package':d.info.get('currentPackageName')}

    def event(self, kind, **fields):
        self.event_seq += 1
        self.events.append({'id':self.event_seq,'kind':kind,'at':time.time()*1000,
                            'viewport':dict(zip(('width','height'),self.connect().window_size())),**fields})

    def select(self, selector):
        target = self.connect()(**selector)
        if target.count != 1:
            raise ValueError(f"Expected one control, found {target.count}; observe and refine selector")
        return target

    def actionable(self, target):
        info = target.info
        if info.get('enabled') is False or info.get('visibleToUser') is False:
            raise ValueError('Target is disabled or invisible; observe and refine selector')
        viewport = dict(zip(('width', 'height'), self.connect().window_size()))
        rect = visible_rect(info.get('visibleBounds') or info.get('bounds'), viewport)
        if not rect:
            raise ValueError('Target has no visible area in the viewport')
        return info, rect

    def toast_start(self):
        device = self.connect()
        try:
            if not callable(getattr(device, 'clear_toast', None)):
                return False
            device.clear_toast()
            return True
        except Exception:
            return False

    def toast_read(self, supported, messages):
        if supported:
            try:
                message = self.connect().last_toast
                if isinstance(message, str) and message and message not in messages:
                    messages.append(message[:2000])
            except Exception:
                return False
        return supported

    def verify_condition(self, condition, messages):
        d = self.connect()
        if condition.get('selector') and not d(**condition['selector']).exists:
            return False
        if condition.get('absent') and d(**condition['absent']).exists:
            return False
        if condition.get('toastContains') and not any(condition['toastContains'] in s for s in messages):
            return False
        if condition.get('package') or condition.get('activity'):
            current = self.foreground()
            if any(current.get(k) != condition[k] for k in ('package', 'activity') if k in condition):
                return False
        return True

    def point(self, x, y):
        w, h = self.connect().window_size()
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x < w and 0 <= y < h):
            raise ValueError("Coordinates outside current viewport")
        return x, y

    def preview(self, after_seq=0, last_event_id=0):
        data = {"server_time": time.time()*1000, "stream_id": "android-" + str(os.getpid()),
                "frame": None, "viewport": None, "busy": False, "paused": self.paused,
                "events": [e for e in list(self.events) if e['id']>last_event_id], "device": {"model": "Android"}}
        data['busy'] = self.busy
        if self.health['locked']:
            data.update(paused=True,pause_reason='device_locked',frame_available=False)
            if not self.health['online']: data.update(paused=False,frame_available=False)
        elif not self.paused:
            if self.stream is None: self.stream = ScreenStream(self.serial)
            self.stream.start()
            data.update(self.stream.snapshot(after_seq))
            # Frame transport must never query Android or share UIAutomator's action channel.
            data['viewport'] = self.preview_viewport
        return data

    def call(self, name, a):
        name = name.removeprefix("android_")
        if name not in SCHEMAS:
            raise ValueError("Unknown tool")
        jsonschema.validate(a, SCHEMAS[name])
        if name in ('screen_frame','screen'):
            return self._call(name,dict(a))
        # All phone operations, including post-action reads, share one device lock.
        if name not in ('doctor','setup'):
            self.connect()
        lock = self.device_lock
        if lock:
            with lock.acquire():
                self.busy = True
                try: return self._call(name,dict(a))
                finally: self.busy = False
        return self._call(name,dict(a))

    def _call(self, name, a):
        if name == "doctor":
            return {"devices": [d.serial for d in adbutils.adb.device_list()], "selected": self.serial,
                    "adb": os.environ.get('ANDROID_USE_ADB') or shutil.which("adb"),
                    "scrcpy": os.environ.get('ANDROID_USE_SCRCPY') or shutil.which("scrcpy"), "python":sys.executable, "version":VERSION}
        if name == 'setup':
            if a['action']=='discover': return self._call('doctor',{})
            if a['action']=='status': return self._call('ready',{})
            if a.get('serial') and a['serial'] not in [d.serial for d in adbutils.adb.device_list()]:
                raise ValueError('Selected serial is not an authorized connected device')
            if self.stream: self.stream.stop();self.stream=None
            self.d = None
            if a.get('serial'): self.serial = a['serial']
            return self._call('ready',{})
        if name == "ready":
            info = self.connect().info
            ready = not self.locked()
            if ready: self.connect().dump_hierarchy()
            self.preview_viewport = dict(zip(('width','height'),self.connect().window_size()))
            self.monitor()
            return {"ready": ready, "state": "ready" if ready else "unlock_required", "serial": self.connect().serial, "info": info}
        if name == "observe":
            mode = a.get("mode", "auto")
            if self.locked(): raise ValueError('Unlock phone before observing')
            return self.capture(mode)
        if name == 'apps':
            query = a.get('query','').lower()
            packages = sorted(p for p in self.connect().app_list() if query in p.lower())
            return {'packages':packages[:a.get('limit',30)],'total_matches':len(packages)}
        if name == "find":
            if self.locked(): raise ValueError('Unlock phone before observing')
            return {"matches": [t.info for t in self.connect()(**a["selector"])]}
        if name in ("screen", "screen_frame", "screen_action"):
            action = a.get("action", "open")
            if name != 'screen_frame':
                self.connect();self.locked();self.monitor()
            if action == "pause":
                self.paused = True
                if self.stream: self.stream.stop()
            if action in ("resume", "open", "refresh") and name != 'screen_frame':
                self.paused = False
            if action == 'refresh' and self.stream:
                self.stream.stop();self.stream=None
            if action == "home": self.call('android_press_button',{'name':'home'})
            return self.preview(a.get('after_seq',0),a.get('last_event_id',0))
        if name == 'batch':
            results=[]
            last_image = None
            for index,step in enumerate(a['steps']):
                try:
                    result=self.call('android_'+step['op'],step['args'])
                    step_image = result.pop('image', None)
                    if 'observation' in result or step_image:
                        last_image = step_image
                    results.append({'index':index,'op':step['op'],'result':result})
                    if result.get('_isError'):
                        return {'_isError':True,'complete':False,'stopped_at':index,'steps':results,
                                'image':last_image,'instruction':'Postcondition failed; inspect returned observation, never replay.'}
                    if (index + 1 < len(a['steps']) and result.get('observation', {}).get('tree_quality', {}).get('screenshot_recommended')
                            and not step['args'].get('expect') and not step['args'].get('verify')):
                        return {'complete':False,'stopped_at':index,'steps':results,'image':last_image,
                                'instruction':'Page requires visual inspection before continuing the batch.'}
                except Exception as exc:
                    return {'_isError':True,'complete':False,'stopped_at':index,'error':str(exc),'steps':results,
                            'instruction':'Observe actual state before any further action; no steps were replayed.'}
            return {'complete':True,'steps':results,'image':last_image}
        d = self.connect()
        if self.locked():
            raise ValueError("Unlock the phone before performing actions")
        if name == 'scroll_find':
            if d(**a['selector']).exists: return {'found':True,'matches':[t.info for t in d(**a['selector'])],'swipes':0}
            w,h=d.window_size();direction=a.get('direction','up')
            start,end=(.75,.3) if direction=='up' else (.3,.75)
            before = self.tree()
            result = self.call('android_swipe',{'x1':w*.5,'y1':h*start,'x2':w*.5,'y2':h*end,
                                               'observation_id':before['observation_id']})
            found=d(**a['selector']).exists
            if not found and not result.get('image'):
                result.update(self.capture('both',result['observation']))
            return {'found':bool(found),'swipes':1,**result}
        if name == 'collect_list':
            return self.collect(a)
        observation_id=a.pop('observation_id',None)
        coordinate_action = name == 'swipe' or (name == 'tap' and 'selector' not in a)
        if coordinate_action and not observation_id:
            raise ValueError('Coordinate tap/swipe requires a fresh observation_id')
        if observation_id: self.validate_observation(observation_id)
        expect=a.pop('expect',None)
        verify=a.pop('verify',None)
        mode=a.pop('mode','auto')
        if expect and verify:
            raise ValueError('Provide expect OR verify, not both')
        condition = {'selector':expect,'timeout':5} if expect else verify
        feedback_supported = self.toast_start() if name in MUTATIONS else False
        messages = []
        verification = {'status':'unconfirmed','check':'none',
                        'reason':'Action dispatch does not prove task success'}
        if name == "tap":
            if "selector" in a and not any(k in a for k in ("x", "y")):
                target=self.select(a['selector']);info,r=self.actionable(target)
                point={'x':(r[0]+r[2])/2,'y':(r[1]+r[3])/2}
                self.event('tap',point=point)
                # Use the validated visible center, not a second stale bounds lookup.
                d.click(point['x'],point['y'])
            elif set(a) == {"x", "y"}:
                self.event('tap',point={'x':a['x'],'y':a['y']})
                d.click(*self.point(a["x"], a["y"]))
            else: raise ValueError("Provide selector OR both x/y")
        elif name == "swipe":
            self.point(a['x1'],a['y1']);self.point(a['x2'],a['y2'])
            self.event('drag',**{'from':{'x':a['x1'],'y':a['y1']},'to':{'x':a['x2'],'y':a['y2']},'duration_ms':a.get('duration',.3)*1000})
            d.swipe(*self.point(a["x1"], a["y1"]), *self.point(a["x2"], a["y2"]), a.get("duration", .3))
        elif name == "type_text":
            target = self.select(a["selector"])
            target_info, _ = self.actionable(target)
            if target_info.get("className") not in ("android.widget.EditText", "android.widget.AutoCompleteTextView", "android.widget.MultiAutoCompleteTextView"):
                raise ValueError("Text input requires an editable field")
            # Secure fields are handed to the user rather than read or modified.
            r = target_info["bounds"]
            for e in ET.fromstring(d.dump_hierarchy()).iter("node"):
                bounds = [int(x) for x in re.findall(r"\d+", e.get("bounds", ""))]
                if bounds == [r["left"], r["top"], r["right"], r["bottom"]] and e.get("password") == "true":
                    raise ValueError("Password field requires user takeover")
            target.set_text(a["text"])
            if target.get_text() != a["text"]:
                raise RuntimeError("Text readback mismatch; do not retry blindly")
            verification = {'status':'verified','check':'text_readback','evidence':{'text':a['text']}}
        elif name == "press_button": d.press(a["name"])
        elif name == "launch_app":
            if not re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", a["package"]):
                raise ValueError("Invalid Android package")
            d.app_start(a["package"])
            deadline=time.monotonic()+10
            while self.foreground().get('package')!=a['package'] and time.monotonic()<deadline:
                time.sleep(.2)
            if self.foreground().get('package')!=a['package']:
                raise RuntimeError("Requested app did not reach foreground; observe before retrying")
            verification = {'status':'verified','check':'foreground_package','evidence':{'package':a['package']}}
        elif name == "wait":
            found=d(**a['selector']).wait(timeout=a.get('timeout',10))
            if not found: raise TimeoutError('Selector did not appear before timeout')
            return {"found":True}
        if condition:
            deadline = time.monotonic() + condition.get('timeout',5)
            while True:
                feedback_supported = self.toast_read(feedback_supported, messages)
                if self.verify_condition(condition, messages):
                    verification = {'status':'verified','check':'postcondition','evidence':condition,
                                    'scope':'Only the supplied postcondition; business success and causality are not inferred'}
                    break
                if time.monotonic() >= deadline:
                    verification = {'status':'failed','check':'postcondition','evidence':condition,
                                    'reason':'Postcondition not observed within timeout; do not replay action'}
                    break
                time.sleep(.1)
        feedback_supported = self.toast_read(feedback_supported, messages)
        capture_failed = False
        try:
            result = self.capture(mode)
        except Exception as exc:
            # The mutation already happened. Preserve that fact even when its read fails.
            capture_failed = True
            result = {'observation':None,'image':None,'observation_error':str(exc),
                      'instruction':'Action was dispatched; obtain a fresh observation, never replay blindly'}
        # Toast cache survives the toast disappearing during hierarchy/screenshot capture.
        feedback_supported = self.toast_read(feedback_supported, messages)
        return {'executed':True,'verification':verification,
                'feedback':{'source':'native_toast_cache','supported':feedback_supported,'messages':messages,
                            'coverage':'Native cached toast only; custom-drawn transient messages may not be exposed'},
                '_isError':capture_failed or verification['status']=='failed',**result}

    def tree_metadata(self):
        d=self.connect();viewport=dict(zip(('width','height'),d.window_size()));app=self.foreground()
        observation={'viewport':viewport,'app':app}
        self.remember(observation)
        return observation

    def collect(self,a):
        rows=[];seen=set();previous=None;reason='page_limit';pages=0
        for page in range(a.get('max_pages',3)):
            tree=self.tree();pages+=1
            if tree['tree_quality']['screenshot_recommended']:
                result=self.capture('auto',tree)
                return {'rows':rows,'pages_observed':pages,'stop_reason':'visual_inspection_required',
                        'complete':False,'coverage':'Hierarchy cannot establish visible list coverage',**result}
            current=[]
            for node in tree['nodes']:
                text=node.get('text')
                if not text or node.get('password')=='true':continue
                if a.get('className') and node.get('class')!=a['className']:continue
                key=(text,node.get('resource-id',''))
                current.append(key)
                if key not in seen: seen.add(key);rows.append({'text':text,'resourceId':node.get('resource-id'),'first_page':page+1})
            fingerprint=tuple(current)
            if a.get('end_selector') and self.connect()(**a['end_selector']).exists:
                reason='end_selector';break
            if fingerprint==previous:
                reason='no_progress';break
            previous=fingerprint
            if page+1<a.get('max_pages',3):
                w,h=self.connect().window_size()
                self.call('android_swipe',{'x1':w*.5,'y1':h*.75,'x2':w*.5,'y2':h*.3,
                                           'observation_id':tree['observation_id']})
        return {'rows':rows,'pages_observed':pages,'stop_reason':reason,'complete':reason=='end_selector',
                'coverage':'Only visible text rows in these pages; repeated identical rows may be merged.',
                'observation':self.tree()}

def tool_result(runtime, params):
    try:
        data = runtime.call(params["name"], params.get("arguments", {}))
        image = data.pop("image", None)
        error = data.pop('_isError',False)
        if params['name']=='android_screen_frame':
            return {'content':[], 'structuredContent':data, 'isError':error}
        content = [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]
        if params['name'] in ('android_screen','android_screen_frame','android_screen_action'):
            summary={k:v for k,v in data.items() if k not in ('frame','events')}
            summary['has_frame']=data.get('frame') is not None
            content=[{'type':'text','text':json.dumps(summary,ensure_ascii=False)}]
        if image: content.append(image)
        result={"content": content, "structuredContent": data, 'isError':error}
        if params['name'] in ('android_ready','android_screen'):
            result['_meta']={'openai/widgetSessionId':'android-use-screen-v0.2.3'}
        return result
    except Exception as e:
        return {"isError": True, "content": [{"type": "text", "text": f"{type(e).__name__}: {e}. If an action was attempted, observe before retrying."}]}

def serve(runtime):
    writing=threading.Lock()
    jobs=queue.Queue(maxsize=32)
    def send(response):
        with writing: print(json.dumps(response,ensure_ascii=False,allow_nan=False,separators=(',',':')),flush=True)
    def work():
        while True:
            req=jobs.get()
            if req is None:return
            send({'jsonrpc':'2.0','id':req['id'],'result':tool_result(runtime,req['params'])})
    worker=threading.Thread(target=work,daemon=True,name='android-tools')
    worker.start()
    try:
      for line in sys.stdin:
        req=None
        try:
            if len(line)>1024*1024:raise ValueError('Request exceeds 1 MiB')
            req = json.loads(line)
            if not isinstance(req,dict) or req.get('jsonrpc')!='2.0':raise ValueError('Invalid JSON-RPC request')
            if "id" not in req: continue
            method = req.get("method")
            if method == "initialize":
                offered=req.get('params',{}).get('protocolVersion')
                protocols=('2025-11-25','2025-06-18','2025-03-26','2024-11-05')
                result = {"protocolVersion": offered if offered in protocols else protocols[0], "capabilities": {"tools": {}, "resources": {}},
                          "serverInfo": {"name": "android-use", "version": VERSION},
                          "instructions": "Call android_ready then observe. Use fresh selectors/screenshots, pixel coordinates. Observe after actions; never replay uncertain mutations. Passwords and authentication require user takeover."}
            elif method == "ping": result = {}
            elif method == "tools/list": result = {"tools": TOOLS}
            elif method == "tools/call":
                if req.get('params',{}).get('name')=='android_screen_frame':
                    result=tool_result(runtime,req['params'])
                else:
                    jobs.put_nowait(req);continue
            elif method == "resources/list": result = {"resources": [{"uri": URI, "name": "Android Screen", "mimeType": "text/html;profile=mcp-app",'_meta':RESOURCE_META}]}
            elif method == "resources/read":
                if req["params"]["uri"] != URI: raise ValueError("Unknown resource")
                result = {"contents": [{"uri": URI, "mimeType": "text/html;profile=mcp-app",
                           "text": (ROOT / "assets/android-screen.html").read_text(encoding="utf-8"),
                           "_meta": RESOURCE_META}]}
            else:
                send({"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": "Method not found"}})
                continue
            response = {"jsonrpc": "2.0", "id": req["id"], "result": result}
        except Exception as e:
            response = {"jsonrpc": "2.0", "id": req.get("id") if isinstance(req, dict) else None,
                        "error": {"code": -32600, "message": str(e)}}
        send(response)
    finally:
        jobs.put(None);worker.join();runtime.close()

if __name__ == "__main__":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--serial")
    p.add_argument("--call", help="Run one tool locally instead of MCP stdio")
    p.add_argument("--args", default="{}")
    args = p.parse_args()
    r = Runtime(args.serial)
    if args.call:
        try: print(json.dumps(tool_result(r, {"name": args.call, "arguments": json.loads(args.args)}), ensure_ascii=False))
        finally: r.close()
    else: serve(r)
