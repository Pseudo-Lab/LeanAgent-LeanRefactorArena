"""Reserve both existing Lean slots for memory-heavy full-source verification."""
from contextlib import contextmanager
import fcntl
from resources import POOL
@contextmanager
def lease():
    handles=[]
    try:
        for slot in (0,1):
            f=(POOL/f'slot-{slot}.lock').open('a')
            handles.append(f)
            fcntl.flock(f,fcntl.LOCK_EX)
        yield
    finally:
        for f in reversed(handles):
            fcntl.flock(f,fcntl.LOCK_UN)
            f.close()
