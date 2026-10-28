from contextvars import ContextVar, Token

from fastapi import Request


_request_ip: ContextVar[str | None] = ContextVar("request_ip", default=None)


def current_request_ip() -> str | None:
    return _request_ip.get()


async def request_ip_middleware(request: Request, call_next):
    client = request.client
    token: Token[str | None] = _request_ip.set(client.host if client else None)
    try:
        return await call_next(request)
    finally:
        _request_ip.reset(token)
