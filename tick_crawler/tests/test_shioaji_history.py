"""Offline tests for the read-only SDK boundary; no credentials or network."""

import logging
import os
from types import ModuleType, SimpleNamespace
import sys
from unittest.mock import Mock

import pytest

from src.data.shioaji_history import HistoryAPIError, open_history_api


@pytest.fixture
def sdk(monkeypatch):
    for name in ("SJ_KEY", "API_KEY", "SJ_API_KEY", "SJ_SEC", "SECRET_KEY", "SJ_SEC_KEY"):
        monkeypatch.delenv(name, raising=False)
    contract = SimpleNamespace(exchange=SimpleNamespace(value="TSE"), code="2330")
    api = SimpleNamespace(
        login=Mock(return_value=["unused account information"]),
        logout=Mock(return_value=True),
        fetch_contracts=Mock(),
        usage=Mock(return_value={
            "connections": 1, "bytes": 32, "limit_bytes": 1000, "remaining_bytes": 968,
        }),
        ticks=Mock(return_value={"ts": [123], "close": [100.0], "volume": [1]}),
        Contracts=SimpleNamespace(Stocks={"2330": contract}),
    )
    module = ModuleType("shioaji")
    module.__version__ = "1.3.2"
    module.Shioaji = Mock(return_value=api)
    monkeypatch.setitem(sys.modules, "shioaji", module)
    return module, api, contract


@pytest.mark.parametrize("aliases", [
    ("SJ_KEY", "SJ_SEC"), ("API_KEY", "SECRET_KEY"), ("SJ_API_KEY", "SJ_SEC_KEY"),
])
def test_session_uses_one_login_and_fetch_without_trading(tmp_path, sdk, aliases):
    module, api, contract = sdk
    env = tmp_path / ".env"
    env.write_text(f"{aliases[0]}=test-key\n{aliases[1]}=test-secret\n")
    with open_history_api(env) as history:
        assert history.version == "1.3.2"
        assert history.resolve("TSE", "2330") is contract
        assert history.resolve("OTC", "2330") is None
        assert history.resolve("TSE", "9999") is None
        assert history.usage()["remaining_bytes"] == 968
        assert history.ticks(contract, "2026-03-02")["ts"] == [123]
    module.Shioaji.assert_called_once_with(simulation=True)
    api.login.assert_called_once_with(
        api_key="test-key", secret_key="test-secret", fetch_contract=False, subscribe_trade=False,
    )
    api.fetch_contracts.assert_called_once_with(contracts_timeout=30000)
    api.usage.assert_called_once_with(timeout=5000)
    api.ticks.assert_called_once_with(contract=contract, date="2026-03-02", timeout=30000)
    api.logout.assert_called_once_with()


def test_exported_credentials_override_dotenv_alias(tmp_path, sdk, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SJ_KEY=file-key\nSJ_SEC=file-secret\n")
    monkeypatch.setenv("SJ_API_KEY", "exported-key")
    monkeypatch.setenv("SJ_SEC_KEY", "exported-secret")
    with open_history_api(env):
        pass
    assert sdk[1].login.call_args.kwargs["api_key"] == "exported-key"
    assert sdk[1].login.call_args.kwargs["secret_key"] == "exported-secret"
    assert "SJ_KEY" not in os.environ


def test_sdk_native_output_and_logs_are_silenced_and_state_restored(tmp_path, sdk, monkeypatch, capfd):
    monkeypatch.setenv("SJ_KEY", "test-key")
    monkeypatch.setenv("SJ_SEC", "test-secret")
    monkeypatch.setenv("SJ_LOG_PATH", "previous.log")
    monkeypatch.setenv("LOG_SENTRY", "previous")
    previous_logging = logging.root.manager.disable

    def noisy_login(**kwargs):
        assert os.environ["SJ_LOG_PATH"] == os.devnull
        print("PRIVATE PYTHON PAYLOAD")
        os.write(1, b"PRIVATE STDOUT PAYLOAD\n")
        os.write(2, b"PRIVATE STDERR PAYLOAD\n")
        logging.getLogger("shioaji").error("PRIVATE LOG PAYLOAD")

    sdk[1].login.side_effect = noisy_login
    with open_history_api(tmp_path / "missing.env"):
        pass
    print("public result")
    captured = capfd.readouterr()
    assert captured.out == "public result\n"
    assert captured.err == ""
    assert os.environ["SJ_LOG_PATH"] == "previous.log"
    assert os.environ["LOG_SENTRY"] == "previous"
    assert logging.root.manager.disable == previous_logging


def test_failed_login_is_sanitized_and_still_logs_out(tmp_path, sdk, monkeypatch):
    monkeypatch.setenv("SJ_KEY", "test-key")
    monkeypatch.setenv("SJ_SEC", "test-secret")
    error = RuntimeError("token=test-secret person_id=PRIVATE")
    error.code = 401
    sdk[1].login.side_effect = error
    sdk[1].logout.side_effect = RuntimeError("private logout payload")
    with pytest.raises(HistoryAPIError, match=r"login failed \(RuntimeError, status=401\)") as caught:
        with open_history_api(tmp_path / "missing.env"):
            pytest.fail("Login failure must not yield an adapter")
    assert "test-secret" not in str(caught.value)
    assert "PRIVATE" not in str(caught.value)
    assert caught.value.__suppress_context__
    sdk[1].logout.assert_called_once_with()
    sdk[1].fetch_contracts.assert_not_called()


def test_tick_failure_does_not_retry_and_logs_out(tmp_path, sdk, monkeypatch):
    monkeypatch.setenv("SJ_KEY", "test-key")
    monkeypatch.setenv("SJ_SEC", "test-secret")
    sdk[1].ticks.side_effect = ValueError("private SDK response")
    with pytest.raises(HistoryAPIError, match=r"ticks failed \(ValueError\)"):
        with open_history_api(tmp_path / "missing.env") as history:
            history.ticks(sdk[2], "2026-03-02")
    sdk[1].ticks.assert_called_once()
    sdk[1].login.assert_called_once()
    sdk[1].logout.assert_called_once()


def test_invalid_usage_fails_closed(tmp_path, sdk, monkeypatch):
    monkeypatch.setenv("SJ_KEY", "test-key")
    monkeypatch.setenv("SJ_SEC", "test-secret")
    sdk[1].usage.return_value["remaining_bytes"] = -1
    with pytest.raises(HistoryAPIError, match="usage failed"):
        with open_history_api(tmp_path / "missing.env") as history:
            history.usage()
    sdk[1].ticks.assert_not_called()
    sdk[1].fetch_contracts.assert_not_called()


def test_usage_only_session_does_not_download_contracts(tmp_path, sdk, monkeypatch):
    monkeypatch.setenv("SJ_KEY", "test-key")
    monkeypatch.setenv("SJ_SEC", "test-secret")
    with open_history_api(tmp_path / "missing.env") as history:
        assert history.usage()["bytes"] == 32
    sdk[1].fetch_contracts.assert_not_called()


def test_absent_credentials_do_not_import_or_construct_sdk(tmp_path, sdk):
    with pytest.raises(HistoryAPIError, match="Missing Shioaji API credentials"):
        with open_history_api(tmp_path / "missing.env"):
            pytest.fail("Missing credentials must stop before login")
    sdk[0].Shioaji.assert_not_called()


def test_second_session_is_rejected_without_another_login(tmp_path, sdk, monkeypatch):
    monkeypatch.setenv("SJ_KEY", "test-key")
    monkeypatch.setenv("SJ_SEC", "test-secret")
    with open_history_api(tmp_path / "missing.env"):
        with pytest.raises(HistoryAPIError, match="already active"):
            with open_history_api(tmp_path / "missing.env"):
                pytest.fail("Nested login must not be allowed")
    sdk[1].login.assert_called_once()
