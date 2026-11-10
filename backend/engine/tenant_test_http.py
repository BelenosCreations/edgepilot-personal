"""Isolated Flask test app for tenant-only read APIs; NEVER imported by app.py.

A real WSGI request implementation of v0.2.17's dormant request contract,
intended solely for synthetic /dev/shm integration tests. No production route
registration, network listener, Public client or active monitor. The factory
requires an explicit environment safety gate and separate local test DB.
It is NOT production hardened or authorized for public deployment.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest

from .identity_auth import COOKIE_NAME, IdentityStore
from .shadow_storage import require_isolated_source
from .tenant_api_gateway import DormantAccountGateway
from .tenant_foundation import TenantAccessError
from .tenant_request_boundary import (
    DormantRequest, DormantRequestBoundary, TenantRequestDenied,
)

TEST_GATE = "EDGE_TENANT_TEST_HTTP_ONLY"
TEST_ORIGIN = "https://edgepilot-test.invalid"
MAX_BODY = 4096


class TestHttpUnavailable(RuntimeError):
    """The WSGI adapter is unavailable outside an approved isolated fixture."""


def create_isolated_test_app(path, identity_store, *, origin=TEST_ORIGIN):
    """Build a real Flask test application, never mounted into live EdgePilot.

    This factory alone provides no listening process or production hooks.
    Only a verified, detached, memory-backed SQLite database is accepted.
    """
    if os.environ.get(TEST_GATE) != "true":
        raise TestHttpUnavailable("Isolated test-only API is disabled")
    db_path, _ = require_isolated_source(path)
    if (type(identity_store) is not IdentityStore or
            Path(identity_store.path).resolve() != db_path):
        raise TestHttpUnavailable("Test identity store does not match fixture")
    if origin != TEST_ORIGIN:
        raise TestHttpUnavailable("Only the synthetic test origin is authorized")

    gateway = DormantAccountGateway(str(db_path), identity_store)
    boundary = DormantRequestBoundary(gateway)
    app = Flask("edgepilot_isolated_tenant_test")
    app.config.update(TESTING=True, MAX_CONTENT_LENGTH=MAX_BODY,
                      PROPAGATE_EXCEPTIONS=False, SERVER_NAME="edgepilot-test.invalid")

    @app.before_request
    def reject_non_fixture_requests():
        # Never trust X-Forwarded-* supplied by a client.
        if request.host != "edgepilot-test.invalid" or not request.is_secure:
            return jsonify({"error":"Isolated test origin required"}), 403
        if request.method not in ("GET","POST","DELETE"):
            return jsonify({"error":"Method disabled"}), 405
        raw=request.environ.get("RAW_URI",request.environ.get("REQUEST_URI",""))
        if "%" in raw or "\\" in raw or ".." in raw or "//" in raw:
            return jsonify({"error":"Noncanonical path"}), 400
        if request.content_length is not None and request.content_length>MAX_BODY:
            return jsonify({"error":"Payload too large"}), 413
        if request.method in ("POST","DELETE"):
            if (request.headers.get("Origin")!=origin or
                request.headers.get("Sec-Fetch-Site","same-origin")!="same-origin"):
                return jsonify({"error":"Forbidden origin"}), 403
            if not request.headers.get("X-Edge-Identity-CSRF"):
                return jsonify({"error":"CSRF required"}), 403

    @app.after_request
    def harden_response(response):
        response.headers["Cache-Control"]="no-store"
        response.headers["Pragma"]="no-cache"
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["X-Frame-Options"]="DENY"
        response.headers["Referrer-Policy"]="no-referrer"
        response.headers["Content-Security-Policy"]="default-src 'none'; frame-ancestors 'none'"
        response.headers["Vary"]="Cookie"
        response.headers.pop("Access-Control-Allow-Origin",None)
        response.headers.pop("Access-Control-Allow-Credentials",None)
        return response

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"error":"Payload too large"}),413

    def process():
        # Cookies are the only accepted identity source; never accept an
        # Authorization bearer token or user_id supplied by the client.
        token=request.cookies.get(COOKIE_NAME,"")
        if identity_store.principal(token) is None:
            return jsonify({"error":"Authentication required"}),401
        try:
            if request.method=="POST":
                if request.mimetype!="application/json":
                    return jsonify({"error":"JSON required"}),415
                payload=request.get_json(silent=False)
                if not isinstance(payload,dict):
                    raise TenantRequestDenied("Invalid tenant request")
            else:
                payload=None
                if request.get_data(cache=False) or request.content_length not in (None,0):
                    raise TenantRequestDenied("Invalid tenant request")
            # MultiDict's len() counts distinct keys, not duplicates.
            # Reject repeated query keys before collapsing any values.
            if any(len(request.args.getlist(key)) != 1 for key in request.args.keys()):
                raise TenantRequestDenied("Invalid tenant request")
            params=request.args.to_dict(flat=True)
            if "before_id" in params:
                before=params["before_id"]
                if not before.isascii() or not before.isdecimal() or len(before)>18:
                    raise TenantRequestDenied("Invalid tenant request")
                params["before_id"]=int(before)
            if "limit" in params:
                limit=params["limit"]
                if not limit.isascii() or not limit.isdecimal() or len(limit)>3:
                    raise TenantRequestDenied("Invalid tenant request")
                params["limit"]=int(limit)
            result=boundary.dispatch(DormantRequest(
                method=request.method,path=request.path,
                token=token,csrf=request.headers.get("X-Edge-Identity-CSRF"),
                payload=payload,params=params))
            return jsonify(result),200
        except (BadRequest, TenantRequestDenied, ValueError, TypeError):
            return jsonify({"error":"Invalid tenant request"}),400
        except TenantAccessError:
            # Same response for a missing account and a foreign account.
            return jsonify({"error":"Account unavailable"}),404

    @app.route("/tenant/accounts",methods=["GET"])
    @app.route("/tenant/selected",methods=["GET","POST","DELETE"])
    @app.route("/tenant/accounts/<account_id>/<view>",methods=["GET"])
    def isolated_tenant_endpoint(account_id=None,view=None):
        return process()

    # No app.run, no endpoint for broker access, no worker scheduler.
    app.config["TENANT_HTTP_TEST_ONLY"]=True
    return app
