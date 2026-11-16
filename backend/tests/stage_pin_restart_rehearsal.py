"""Fresh-process, read-only inventory of a synthetic parking fixture."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys


def entry_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def read_entry(path, limit):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return "absent", None, None
    except OSError:
        return "unreadable", None, None

    try:
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                return "unreadable", None, entry_identity(opened)
            data = stream.read(limit + 1)
            identity = entry_identity(opened)
            if entry_identity(os.fstat(stream.fileno())) != identity:
                return "changed", None, identity
        try:
            named = path.lstat()
        except FileNotFoundError:
            return "changed", None, identity
        if entry_identity(named) != identity:
            return "changed", None, identity
    except OSError:
        return "unreadable", None, None

    return ("oversized", None, identity) if len(data) > limit else ("present", data, identity)


def read_digest(observation):
    state, data = observation
    if state == "oversized":
        return "malformed", None
    if state != "present":
        return state, None
    if not re.fullmatch(rb"[0-9a-f]{1,64}", data):
        return "malformed", None
    if len(data) < 64:
        return "partial", None
    return "complete", data.decode("ascii")


def observe_record(records, basename, key, source_kind, read):
    body_state, body = read(records / f"{basename}.json", 65536)
    seal_state, seal = read(records / f"{basename}.mac", 64)
    states = (body_state, seal_state)
    digest = None
    if "changed" in states:
        state = "changed"
    elif states == ("absent", "absent"):
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


def inventory(root, key, source_kind, checkpoint=None):
    folder = root / "independent-records"
    first_reads = {}

    def read(path, limit):
        observation = read_entry(path, limit)
        first_reads[path] = (limit, observation)
        if checkpoint is not None and path == folder / "location.json":
            checkpoint("after-record-body")
        return observation[:2]

    records = {name: observe_record(folder, name, key, source_kind, read)
               for name in ("location", "previous-location")}
    if checkpoint is not None:
        checkpoint("after-records")
    authenticated = {record["digest"] for record in records.values()
                     if record["state"] == "authenticated"}

    def observe(path):
        state, digest = read_digest(read(path, 64))
        if state == "complete":
            state = "signed-record" if digest in authenticated else "unmatched"
        return {"state": state, "digest": digest}

    active = observe(root / "independently-retained-location.sha256")
    staged = observe(root / "pending-location.sha256")
    if checkpoint is not None:
        checkpoint("after-pins")
    changed = [
        path.relative_to(root).as_posix()
        for path, (limit, first) in first_reads.items()
        if first[0] == "changed" or read_entry(path, limit) != first
    ]
    if changed:
        # A mixed observation cannot establish even a pin-to-record match.
        return {"status": "ambiguous", "changed": changed}

    confirmed = active["state"] == "signed-record" and staged["state"] == "absent"
    return {
        "records": records,
        "active": active,
        "staged": staged,
        "status": "active-pin-observed" if confirmed else "ambiguous",
    }


def main():
    fixture = json.load(sys.stdin)
    args = (Path(fixture["root"]), bytes.fromhex(fixture["key"]), fixture["kind"])
    if "sync_fd" not in fixture:
        result = inventory(*args)
    else:
        with socket.socket(fileno=fixture["sync_fd"]) as sync:
            sync.settimeout(10)

            def checkpoint(phase):
                if phase == fixture["phase"]:
                    sync.sendall(b"R")
                    if sync.recv(1) != b"W":
                        raise RuntimeError("Synthetic writer did not finish")

            result = inventory(*args, checkpoint=checkpoint)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
