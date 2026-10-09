"""Read-only local scrcpy stream, decoded to bounded cached preview frames."""
import base64
import collections
import io
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time

import adbutils

class ScreenStream:
    def __init__(self, serial):
        self.serial = serial
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.sock = None
        self.process = None
        self.frame = None
        self.seq = 0
        self.source = 'starting'
        self.error = None
        self.model = 'Android'
        self.stream_id = secrets.token_hex(8)
        self.logs = collections.deque(maxlen=10)
        self.last_request = time.monotonic()
        self.encode_condition = threading.Condition()
        self.pending_picture = None
        self.encoder_done = False

    def start(self):
        self.last_request = time.monotonic()
        if self.thread and self.thread.is_alive(): return
        self.stop_event.clear()
        self.stream_id = secrets.token_hex(8)
        self.thread = threading.Thread(target=self.run, daemon=True, name='android-preview')
        self.thread.start()

    def snapshot(self, after_seq=0):
        self.last_request = time.monotonic()
        with self.lock:
            frame = self.frame.copy() if self.frame and self.frame['seq'] > after_seq else None
            return {'frame': frame, 'frame_available': self.frame is not None,
                    'source': self.source, 'stream_error': self.error, 'stream_id': self.stream_id,
                    'device': {'model': self.model},
                    'viewport': {k:self.frame[k] for k in ('width','height')} if self.frame else None}

    def publish(self, image):
        b = io.BytesIO()
        image.save(b, format='JPEG', quality=72)
        with self.lock:
            self.seq += 1
            self.frame = {'seq': self.seq, 'data': base64.b64encode(b.getvalue()).decode(),
                          'mimeType': 'image/jpeg', 'width': image.width, 'height': image.height,
                          'published_at': time.time()*1000}

    def queue_picture(self, picture):
        # A single replaceable decoded picture prevents slow JPEG work from
        # backing up the USB reader. H264 reference packets are never skipped.
        with self.encode_condition:
            self.pending_picture = picture
            self.encode_condition.notify()

    def encode_latest(self):
        while True:
            with self.encode_condition:
                self.encode_condition.wait_for(lambda: self.pending_picture is not None or self.encoder_done)
                if self.encoder_done:
                    return
                picture, self.pending_picture = self.pending_picture, None
            try:
                self.publish(picture.to_image())
            except Exception as exc:
                self.error = f'{type(exc).__name__}: {exc}'[:300]

    def run(self):
        try:
            self.scrcpy()
        except Exception as exc:
            self.cleanup()
            if not self.stop_event.is_set():
                self.error = f'{type(exc).__name__}: {exc}'[:300]
                self.source = 'screenshot'
                self.fallback()
        finally:
            self.cleanup()

    def scrcpy(self):
        import av
        executable = os.environ.get('ANDROID_USE_SCRCPY') or shutil.which('scrcpy')
        if not executable: raise RuntimeError('scrcpy is not installed')
        server = Path(os.environ.get('ANDROID_USE_SCRCPY_SERVER') or str(Path(executable).parent/'scrcpy-server'))
        if not server.is_file(): raise RuntimeError('Matching scrcpy-server file is missing')
        version = os.environ.get('ANDROID_USE_SCRCPY_VERSION')
        if not version:
            found = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=5,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            match = re.search(r'scrcpy\s+(\d+\.\d+(?:\.\d+)?)', found.stdout)
            if not match: raise RuntimeError('Cannot determine scrcpy server version')
            version = match.group(1)
        # raw_stream is a documented scrcpy server mode, avoiding version-specific packet headers.
        device = adbutils.adb.device(self.serial)
        remote = '/data/local/tmp/android-use-scrcpy-' + version + '.jar'
        device.sync.push(str(server), remote)
        self.model = device.getprop('ro.product.model')
        scid = secrets.randbits(31)
        command = ['CLASSPATH='+remote, 'app_process','/','com.genymobile.scrcpy.Server',version,
                   f'scid={scid:08x}', 'tunnel_forward=true', 'audio=false', 'control=false',
                   'cleanup=false', 'raw_stream=true', 'max_size=1400', 'max_fps=60',
                   'video_bit_rate=2000000', 'video_codec=h264', 'log_level=warn']
        adb = os.environ.get('ANDROID_USE_ADB') or shutil.which('adb')
        if not adb: raise RuntimeError('adb is not installed')
        self.process = subprocess.Popen([adb,'-s',self.serial,'shell',*command], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        output = self.process.stdout
        def drain():
            for line in output:
                self.logs.append(line.decode('utf-8',errors='replace').strip())
        threading.Thread(target=drain, daemon=True).start()
        deadline = time.monotonic()+8
        while not self.stop_event.is_set():
            try:
                self.sock = device.create_connection(adbutils.Network.LOCAL_ABSTRACT, f'scrcpy_{scid:08x}')
                break
            except adbutils.AdbError:
                if time.monotonic() > deadline or self.process.poll() is not None:
                    raise RuntimeError('scrcpy connection failed: '+' '.join(self.logs))
                self.stop_event.wait(.15)
        if self.stop_event.is_set(): return
        self.sock.settimeout(1)
        codec = av.CodecContext.create('h264','r')
        self.source = 'scrcpy'
        self.encoder_done = False
        encoder = threading.Thread(target=self.encode_latest, daemon=True, name='android-jpeg')
        encoder.start()
        try:
            while not self.stop_event.is_set() and time.monotonic()-self.last_request < 30:
                try: data = self.sock.recv(65536)
                except socket.timeout: continue
                if not data: raise ConnectionError('scrcpy disconnected')
                latest = None
                for packet in codec.parse(data):
                    for frame in codec.decode(packet):
                        latest = frame
                if latest is not None:
                    self.queue_picture(latest)
        finally:
            with self.encode_condition:
                self.encoder_done = True
                self.pending_picture = None
                self.encode_condition.notify()
            encoder.join(timeout=4)

    def fallback(self):
        device = adbutils.adb.device(self.serial)
        while not self.stop_event.is_set() and time.monotonic()-self.last_request < 30:
            try:
                self.publish(device.screenshot())
            except Exception as exc:
                self.error = f'{type(exc).__name__}: {exc}'[:300]
                with self.lock: self.frame = None
            self.stop_event.wait(.8)

    def cleanup(self):
        if self.sock:
            try: self.sock.close()
            except OSError: pass
            self.sock = None
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=3)
                except subprocess.TimeoutExpired: self.process.kill()
            self.process = None

    def stop(self):
        self.stop_event.set()
        if self.sock:
            try: self.sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        if self.thread and self.thread.is_alive(): self.thread.join(timeout=4)
        self.cleanup()
        with self.lock: self.frame = None
