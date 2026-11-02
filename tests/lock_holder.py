import sys
import time
from pathlib import Path

from printguard.lock import ProcessLock

lock = ProcessLock(Path(sys.argv[1]))
lock.acquire()
print("locked", flush=True)
time.sleep(120)
