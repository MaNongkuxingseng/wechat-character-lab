"""Windows DPAPI helpers for secrets stored by the local application."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class SecretStoreUnavailable(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(value: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(value)
    return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect_secret(value: str) -> bytes:
    return _crypt(value.encode("utf-8"), protect=True)


def unprotect_secret(value: bytes) -> str:
    return _crypt(value, protect=False).decode("utf-8")


def _crypt(value: bytes, *, protect: bool) -> bytes:
    if os.name != "nt":
        raise SecretStoreUnavailable("windows_dpapi_unavailable")

    crypt32 = ctypes.WinDLL("Crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source, source_buffer = _blob(value)
    target = _DataBlob()
    description = wintypes.LPWSTR()
    if protect:
        ok = crypt32.CryptProtectData(
            ctypes.byref(source), "WeChat Character Lab provider key", None, None, None, 0,
            ctypes.byref(target),
        )
    else:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(source), ctypes.byref(description), None, None, None, 0,
            ctypes.byref(target),
        )
    del source_buffer
    if not ok:
        raise SecretStoreUnavailable("windows_dpapi_operation_failed")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)
        if description:
            kernel32.LocalFree(description)
