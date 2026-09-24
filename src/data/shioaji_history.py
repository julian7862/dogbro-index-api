"""Read-only Shioaji session for the standalone historical-data downloader.

The SDK is imported only when a session is opened. Native SDK diagnostics may
contain account identifiers, so stdout/stderr and logging are silenced for the
whole session, including login failures and logout. Use this in a dedicated
CLI process; the output redirection affects every thread in that process.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import importlib
import logging
import os
from pathlib import Path
import re
import sys
import threading
from typing import Any, Callable, TypeVar


_SESSION_LOCK = threading.Lock()
_T = TypeVar("_T")
_USAGE_FIELDS = ("connections", "bytes", "limit_bytes", "remaining_bytes")


class HistoryAPIError(RuntimeError):
    """An SDK failure whose message contains no raw SDK response or credentials."""


def _safe_error(operation: str, error: Exception) -> HistoryAPIError:
    name = type(error).__name__
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}", name):
        name = "SDKError"
    # SDK error text can contain the complete login payload. Only a bounded
    # HTTP-style status is useful here; do not stringify the error itself.
    code = getattr(error, "code", None)
    status = ""
    if isinstance(code, (int, str)) and re.fullmatch(r"[1-5][0-9]{2}", str(code)):
        status = f", status={code}"
    return HistoryAPIError(f"Shioaji {operation} failed ({name}{status})")


def _call(operation: str, function: Callable[[], _T]) -> _T:
    try:
        return function()
    except Exception as error:
        raise _safe_error(operation, error) from None


def _flush_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError):
            pass


@contextmanager
def _quiet_sdk_output() -> Iterator[None]:
    """Suppress Python logging, Python streams, and C/native fd output."""
    previous_env = {name: os.environ.get(name) for name in ("SJ_LOG_PATH", "LOG_SENTRY")}
    previous_logging = logging.root.manager.disable
    saved_fds: dict[int, int] = {}
    try:
        os.environ["SJ_LOG_PATH"] = os.devnull
        # Older SDK releases test this as a string's truth value.
        os.environ["LOG_SENTRY"] = ""
        _flush_output()
        with open(os.devnull, "w", encoding="utf-8") as quiet:
            try:
                for fd in (1, 2):
                    saved_fds[fd] = os.dup(fd)
                    os.dup2(quiet.fileno(), fd)
                logging.disable(logging.CRITICAL)
                with redirect_stdout(quiet), redirect_stderr(quiet):
                    yield
            finally:
                _flush_output()
                for fd, original in saved_fds.items():
                    try:
                        os.dup2(original, fd)
                    finally:
                        os.close(original)
    finally:
        logging.disable(previous_logging)
        for name, previous in previous_env.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous


def _credentials(env_path: Path) -> tuple[str, str]:
    from dotenv import dotenv_values

    file_values = dotenv_values(env_path) if env_path.is_file() else {}

    def read(names: tuple[str, ...]) -> str:
        # An explicitly exported credential takes precedence over every alias
        # in the dotenv file. Do not add secrets to the process environment.
        for source in (os.environ, file_values):
            for name in names:
                value = source.get(name)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    api_key = read(("SJ_KEY", "API_KEY", "SJ_API_KEY"))
    secret_key = read(("SJ_SEC", "SECRET_KEY", "SJ_SEC_KEY"))
    if not api_key or not secret_key:
        raise HistoryAPIError(
            "Missing Shioaji API credentials: set SJ_KEY/SJ_SEC, "
            "API_KEY/SECRET_KEY, or SJ_API_KEY/SJ_SEC_KEY in the environment or dotenv file"
        )
    return api_key, secret_key


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    if hasattr(value, "dict"):
        return dict(value.dict())
    raise TypeError("Unexpected SDK response type")


class ShioajiHistoryAPI:
    """Narrow market-data-only adapter; calls never reconnect or retry."""

    def __init__(self, api: Any, version: str):
        self._api = api
        self.version = version
        self._contracts_loaded = False

    def usage(self) -> dict[str, int]:
        def get_usage() -> dict[str, int]:
            result = self._api.usage(timeout=5000)
            values = _as_mapping(result)
            usage: dict[str, int] = {}
            for field in _USAGE_FIELDS:
                value = values[field]
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError("Invalid usage counter")
                usage[field] = value
            return usage

        return _call("usage", get_usage)

    def resolve(self, exchange: str, code: str) -> Any | None:
        if not self._contracts_loaded:
            _call("fetch_contracts", lambda: self._api.fetch_contracts(contracts_timeout=30000))
            self._contracts_loaded = True

        def get_contract() -> Any | None:
            try:
                contract = self._api.Contracts.Stocks[code]
            except (KeyError, AttributeError):
                return None
            if contract is None:
                return None
            actual_exchange = getattr(contract.exchange, "value", contract.exchange)
            if str(actual_exchange).upper() != str(exchange).upper():
                return None
            if str(contract.code) != str(code):
                return None
            return contract

        return _call("resolve", get_contract)

    def ticks(self, contract: Any, date: str) -> dict[str, list[Any]]:
        def get_ticks() -> dict[str, list[Any]]:
            result = self._api.ticks(contract=contract, date=date, timeout=30000)
            if result is None:
                return {}
            values = _as_mapping(result)
            arrays: dict[str, list[Any]] = {}
            for field, value in values.items():
                if not isinstance(field, str) or isinstance(value, (str, bytes, Mapping)):
                    raise ValueError("Invalid tick array")
                arrays[field] = list(value)
            return arrays

        return _call("ticks", get_ticks)


@contextmanager
def open_history_api(env_path: Path) -> Iterator[ShioajiHistoryAPI]:
    """Open one simulation session and always log out.

    No CA is activated and no order/subscription methods are exposed. The
    installed SDK is used without upgrading it. An SDK error stops the caller;
    this adapter has no retry or reconnection loop. Contracts load once on
    first resolution, so usage-only checks never download contracts.
    """
    if not _SESSION_LOCK.acquire(blocking=False):
        raise HistoryAPIError("A historical Shioaji session is already active in this process")
    try:
        with _quiet_sdk_output():
            api_key, secret_key = _credentials(Path(env_path))
            sdk = _call("import", lambda: importlib.import_module("shioaji"))
            api = _call("initialize", lambda: sdk.Shioaji(simulation=True))
            try:
                _call(
                    "login",
                    lambda: api.login(
                        api_key=api_key,
                        secret_key=secret_key,
                        fetch_contract=False,
                        subscribe_trade=False,
                    ),
                )
                yield ShioajiHistoryAPI(api, str(getattr(sdk, "__version__", "unknown")))
            finally:
                error_in_flight = sys.exc_info()[0] is not None
                try:
                    result = _call("logout", api.logout)
                    if result is False:
                        raise HistoryAPIError("Shioaji logout failed (SDK returned false)")
                except HistoryAPIError:
                    # Preserve the original error while still attempting to
                    # release a connection after a partial/failed login.
                    if not error_in_flight:
                        raise
    finally:
        _SESSION_LOCK.release()
