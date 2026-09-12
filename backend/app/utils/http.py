"""Small HTTP helpers so error responses are consistent across routers."""

from typing import NoReturn

from fastapi import HTTPException


def bad_request(detail: str) -> NoReturn:
    raise HTTPException(status_code=400, detail=detail)


def not_found(detail: str) -> NoReturn:
    raise HTTPException(status_code=404, detail=detail)


def conflict(detail: str) -> NoReturn:
    raise HTTPException(status_code=409, detail=detail)


def too_large(detail: str) -> NoReturn:
    raise HTTPException(status_code=413, detail=detail)


def unprocessable(detail: str) -> NoReturn:
    raise HTTPException(status_code=422, detail=detail)
