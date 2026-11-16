"""Fresh-process, read-only inventory of a synthetic parking fixture."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys


def read_entry(path, limit):
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
            data = stream.read(limit + 1)
        if not os.path.samestat(identity, path.lstat()):
            return "unreadable", None
    except OSError:
        return "unreadable", None

    return ("oversized", None) if len(data) > limit else ("present", data)


def read_digest(path):
    state, data = read_entry(path, 64)
    if state == "oversized":
        return "malformed", None
    if state != "present":
        return state, None
    if not re.fullmatch(rb"[0-9a-f]{1,64}", data):
        return "malformed", None
    if len(data) < 64:
        return "partial", None
    return "complete", data.decode("ascii")


def observe_record(records, basename, key, source_kind):
    body_state, body = read_entry(records / f"{basename}.json", 65536)
    seal_state, seal = read_entry(records / f"{basename}.mac", 64)
    states = (body_state, seal_state)
    digest = None
    if states == ("absent", "absent"):
        state = "absent"
    elif "unreadable" in states:
        state = "unreadable"
    elif "absent" in states:
        state = "incomplete"
    elif body_state == "oversized":
        state = "invalid-body"
    elif seal_state == "oversized" or not hmac.compare_digest(
            hmac.new(key, body, hashlib.sha256).hexdigest().encode("ascii"), seal):
        state = "invalid-seal"
    else:
        try:
            record = json.loads(body)
        except (ValueError, UnicodeError):
            record = None
        if not isinstance(record, dict) or not isinstance(record.get("source_kind"), str):
            state = "invalid-body"
        elif record["source_kind"] != source_kind:
            state = "source-mismatch"
        else:
            state = "authenticated"
            digest = hashlib.sha256(body).hexdigest()
    return {"state": state, "body": body_state, "seal": seal_state, "digest": digest}


def inventory(root, key, source_kind):
    folder = root / "independent-records"
    records = {name: observe_record(folder, name, key, source_kind)
               for name in ("location", "previous-location")}
    authenticated = {record["digest"] for record in records.values()
                     if record["state"] == "authenticated"}

    def observe(path):
        state, digest = read_digest(path)
        if state == "complete":
            state = "signed-record" if digest in authenticated else "unmatched"
        return {"state": state, "digest": digest}

    active = observe(root / "independently-retained-location.sha256")
    staged = observe(root / "pending-location.sha256")
    confirmed = active["state"] == "signed-record" and staged["state"] == "absent"
    return {
        "records": records,
        "active": active,
        "staged": staged,
        "status": "active-pin-observed" if confirmed else "ambiguous",
    }


if __name__ == "__main__":
    fixture = json.load(sys.stdin)
    result = inventory(Path(fixture["root"]), bytes.fromhex(fixture["key"]), fixture["kind"])
    print(json.dumps(result))
