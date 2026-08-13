"""One pipeline run at a time — a slow run and the next schedule must not collide."""
from __future__ import annotations

import fcntl


def acquire_lock(path):
    """Take the run lock. Returns the open lock file (keep it alive for the
    whole run; closing releases), or None if another run holds it."""
    f = open(path, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except OSError:
        f.close()
        return None
