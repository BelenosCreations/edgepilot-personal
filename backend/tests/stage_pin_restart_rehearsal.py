"""Fresh-process, read-only inventory of a synthetic parking fixture."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys


def read_digest(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return "absent", None
    except OSError:
        return "unreadable", None

    try:
        with os.fdopen(fd, "rb") as stream:
            identity = os.fstat(stream.fileno())
            if not stat.S_ISREG(identity.st_mode):
                return "unreadable", None
            data = stream.read(65)
        if not os.path.samestat(identity, path.lstat()):
            return "unreadable", None
    except OSError:
        return "unreadable", None

    if not re.fullmatch(rb"[0-9a-f]{1,64}", data):
        return "malformed", None
    if len(data) < 64:
        return "partial", None
    return "complete", data.decode("ascii")


def inventory(root, key, source_kind):
    records = root / "independent-records"
    authenticated = set()
    for basename in ("location", "previous-location"):
        body = (records / f"{basename}.json").read_bytes()
        seal = (records / f"{basename}.mac").read_bytes()
        expected = hmac.new(key, body, hashlib.sha256).hexdigest().encode("ascii")
        if hmac.compare_digest(expected, seal) and json.loads(body)["source_kind"] == source_kind:
            authenticated.add(hashlib.sha256(body).hexdigest())

    def observe(path):
        state, digest = read_digest(path)
        if state == "complete":
            state = "signed-record" if digest in authenticated else "unmatched"
        return {"state": state, "digest": digest}

    active = observe(root / "independently-retained-location.sha256")
    staged = observe(root / "pending-location.sha256")
    confirmed = active["state"] == "signed-record" and staged["state"] == "absent"
    return {
        "active": active,
        "staged": staged,
        "status": "active-pin-observed" if confirmed else "ambiguous",
    }


if __name__ == "__main__":
    fixture = json.load(sys.stdin)
    result = inventory(Path(fixture["root"]), bytes.fromhex(fixture["key"]), fixture["kind"])
    print(json.dumps(result))
