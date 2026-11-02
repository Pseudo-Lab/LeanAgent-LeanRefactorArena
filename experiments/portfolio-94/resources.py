"""At most two heavy Lean jobs; root build occupies slot zero while its marker exists."""
from pathlib import Path
from contextlib import contextmanager
import fcntl,time,os
HERE=Path(__file__).resolve().parent
POOL=HERE.parent.parent/'runs/portfolio-94/resource-pool'
POOL.mkdir(parents=True,exist_ok=True)
@contextmanager
def lease():
 while True:
  slots=[1] if (POOL/'root-build.active').exists() else [0,1]
  chosen=None
  for slot in slots:
   f=(POOL/f'slot-{slot}.lock').open('a')
   try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);chosen=f;break
   except BlockingIOError:f.close()
  if chosen is not None:break
  time.sleep(0.5)
 try:yield
 finally:fcntl.flock(chosen,fcntl.LOCK_UN);chosen.close()
