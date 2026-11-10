"""Dormant Public HTTPS wire adapter: two fixed endpoints, hard-disabled network.

This is a real HTTP/1.1 over verified TLS implementation for **future** use,
but v0.2.21 has NO network activation mechanism. Testing uses a fake
connection on real request/response parsing paths. The only public method
that could create a socket, send_live(), unconditionally raises.

A subsequent separately approved revision must introduce a reviewed
activation ceremony, account binding, credentials, and on-call controls.
An environment variable cannot enable this network path.
"""
from __future__ import annotations

from dataclasses import dataclass
import http.client
import json
import ssl
from typing import Any

HOST="api.public.com"
PORT=443
TOKEN_PATH="/userapiauthservice/personal/access-tokens"
ACCOUNTS_PATH="/userapigateway/trading/account"
CONNECTION_TIMEOUT_SECONDS=5
MAX_JSON_BYTES=64*1024
MAX_TOKEN_BYTES=4*1024
# Deliberately no environment or configuration switch.
NETWORK_ENABLED=False
_ALLOWED=frozenset((("POST",TOKEN_PATH),("GET",ACCOUNTS_PATH)))


class PublicWireDenied(RuntimeError):
    """Always a fixed non-secret error code (never an underlying HTTP error)."""
    _CODES=frozenset((
        "NETWORK_DISABLED","METHOD_OR_PATH_DENIED","INVALID_REQUEST",
        "INVALID_RESPONSE","PAYLOAD_TOO_LARGE","AUTH_REJECTED",
        "RATE_LIMITED","PROVIDER_UNAVAILABLE","UNEXPECTED_STATUS",
        "TLS_OR_NETWORK_FAILURE",
    ))
    def __init__(self,code):
        self.code=code if code in self._CODES else "INVALID_RESPONSE"
        super().__init__(self.code)


@dataclass(frozen=True)
class WireRequest:
    method:str
    path:str
    body:bytes|None
    authorization:str|None=None

    def __repr__(self):
        # Don't ever print a secret or bearer token in debug logs.
        return "<PublicWireRequest redacted>"


@dataclass(frozen=True)
class WireReply:
    body:dict[str,Any]
    status:int=200


def prepare_token_request(secret,*,validity_minutes=5):
    if (not isinstance(secret,str) or not 20<=len(secret)<=2048
        or not isinstance(validity_minutes,int) or isinstance(validity_minutes,bool)
        or validity_minutes!=5 or "\r" in secret or "\n" in secret or "\0" in secret):
        raise PublicWireDenied("INVALID_REQUEST")
    body=json.dumps({"secret":secret,"validityInMinutes":5},
                    separators=(",",":"),ensure_ascii=True).encode("utf-8")
    if len(body)>MAX_TOKEN_BYTES:
        raise PublicWireDenied("PAYLOAD_TOO_LARGE")
    return WireRequest("POST",TOKEN_PATH,body)


def prepare_accounts_request(token):
    if (not isinstance(token,str) or not 16<=len(token)<=4096
        or any((ord(c)<33 or ord(c)>126) for c in token)
        or any(c in token for c in ("\\",'"'))):
        raise PublicWireDenied("INVALID_REQUEST")
    return WireRequest("GET",ACCOUNTS_PATH,None,authorization=token)


def _pairs_unique(pairs):
    value={}
    for k,v in pairs:
        if k in value:
            raise PublicWireDenied("INVALID_RESPONSE")
        value[k]=v
    return value


def _status(status):
    if type(status) is not int:
        raise PublicWireDenied("INVALID_RESPONSE")
    if status in (401,403):
        raise PublicWireDenied("AUTH_REJECTED")
    if status==429:
        raise PublicWireDenied("RATE_LIMITED")
    if status in (408,500,502,503,504):
        raise PublicWireDenied("PROVIDER_UNAVAILABLE")
    # No redirects, retries, 201 or other response codes permitted.
    if status!=200:
        raise PublicWireDenied("UNEXPECTED_STATUS")


def _validate_request(req):
    if type(req) is not WireRequest or (req.method,req.path) not in _ALLOWED:
        raise PublicWireDenied("METHOD_OR_PATH_DENIED")
    if req.method=="GET":
        if req.body is not None or req.authorization is None:
            raise PublicWireDenied("INVALID_REQUEST")
        # Revalidate even if the caller forged the dataclass.
        prepare_accounts_request(req.authorization)
    else:
        if req.authorization is not None or not isinstance(req.body,bytes):
            raise PublicWireDenied("INVALID_REQUEST")
        if len(req.body)>MAX_TOKEN_BYTES:
            raise PublicWireDenied("PAYLOAD_TOO_LARGE")
        try:
            parsed=json.loads(req.body)
        except (ValueError,UnicodeDecodeError):
            raise PublicWireDenied("INVALID_REQUEST") from None
        if not isinstance(parsed,dict) or set(parsed)!={"secret","validityInMinutes"}:
            raise PublicWireDenied("INVALID_REQUEST")
        if parsed["validityInMinutes"]!=5 or type(parsed["validityInMinutes"]) is not int:
            raise PublicWireDenied("INVALID_REQUEST")
        prepare_token_request(parsed["secret"])


def _perform_with_connection(req,conn):
    """Real HTTPSConnection request parser; tests pass a socket-free fake.

    No user-supplied URL/host/path, no redirect handling, no cookies,
    default proxy, response decompression, or retry. No response logging.
    """
    _validate_request(req)
    headers={"Accept":"application/json","Accept-Encoding":"identity",
             "Connection":"close"}
    if req.method=="POST":
        headers["Content-Type"]="application/json"
    else:
        headers["Authorization"]="Bearer "+req.authorization
    try:
        conn.request(req.method,req.path,body=req.body,headers=headers)
        response=conn.getresponse()
        status=response.status
        _status(status)
        content_type=response.getheader("Content-Type","")
        if (not isinstance(content_type,str) or
            content_type.split(";",1)[0].strip().lower()!="application/json"):
            raise PublicWireDenied("INVALID_RESPONSE")
        content_encoding=response.getheader("Content-Encoding","identity")
        if content_encoding not in (None,"identity"):
            raise PublicWireDenied("INVALID_RESPONSE")
        length=response.getheader("Content-Length")
        if length is not None:
            if not length.isdecimal() or int(length)>MAX_JSON_BYTES:
                raise PublicWireDenied("PAYLOAD_TOO_LARGE")
        raw=response.read(MAX_JSON_BYTES+1)
        if len(raw)>MAX_JSON_BYTES:
            raise PublicWireDenied("PAYLOAD_TOO_LARGE")
        body=json.loads(raw.decode("utf-8"),object_pairs_hook=_pairs_unique)
        if not isinstance(body,dict):
            raise PublicWireDenied("INVALID_RESPONSE")
        return WireReply(body)
    except PublicWireDenied:
        raise
    except (OSError,TimeoutError,ssl.SSLError,http.client.HTTPException,
            UnicodeError,ValueError,TypeError,OverflowError):
        raise PublicWireDenied("TLS_OR_NETWORK_FAILURE") from None
    finally:
        conn.close()


class StrictPublicHTTPS:
    """Prepared HTTPS client with no currently issuable live permission."""

    @staticmethod
    def _connection():
        # Future review must assess DNS and TLS interception and network
        # policy. Stdlib HTTPSConnection verifies certificate and hostname.
        context=ssl.create_default_context()
        context.check_hostname=True
        context.verify_mode=ssl.CERT_REQUIRED
        return http.client.HTTPSConnection(
            HOST,PORT,timeout=CONNECTION_TIMEOUT_SECONDS,context=context)

    def send_live(self,request):
        # No flag or user input can grant network permission in v0.2.21.
        raise PublicWireDenied("NETWORK_DISABLED")

    def send_synthetic_on_fake(self,request,connection):
        """Use same request/response code with a pre-constructed fake.

        Deliberately require a distinct fake marker, never a real
        http.client connection. The fake can record requests only.
        """
        if (not getattr(connection,"edgepilot_fake_public_connection",False)
            or isinstance(connection,http.client.HTTPConnection)):
            raise PublicWireDenied("NETWORK_DISABLED")
        return _perform_with_connection(request,connection)

    def submit_order(self,*args,**kwargs):
        raise PublicWireDenied("METHOD_OR_PATH_DENIED")

    def transfer_funds(self,*args,**kwargs):
        raise PublicWireDenied("METHOD_OR_PATH_DENIED")
