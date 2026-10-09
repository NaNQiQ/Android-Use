"""Per-device cross-process advisory lock; released by the OS after a crash."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile
import threading

class DeviceLock:
    def __init__(self, serial):
        self.thread_lock = threading.RLock()
        state = Path(os.environ.get('ANDROID_USE_STATE_DIR', str(Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir()))/'AndroidUse')))
        state.mkdir(parents=True,exist_ok=True)
        self.path = state / ('device-'+hashlib.sha256(serial.encode()).hexdigest()[:16]+'.lock')
        self.depth = 0
        self.file = None

    @contextmanager
    def acquire(self):
        with self.thread_lock:
            if self.depth == 0:
                f = open(self.path,'a+b')
                f.seek(0,2)
                if f.tell()==0: f.write(b'0');f.flush()
                f.seek(0)
                try:
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                except OSError:
                    f.close()
                    raise RuntimeError('device_busy: another Android Use process owns this device')
                self.file = f
            self.depth += 1
            try: yield
            finally:
                self.depth -= 1
                if self.depth == 0:
                    self.file.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
                    self.file.close();self.file=None
