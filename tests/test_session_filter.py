"""Tests for MT5Executor._check_session_filter — UTC hour vs per-symbol session config.

Sessions (UTC):
  Asian:    00:00-08:00
  London:   07:00-16:00
  New York: 12:00-21:00

Overlap windows:
  07:00-08:00  — Asian + London
  12:00-16:00  — London + New York

Hours 21:00-24:00 are not covered by any session and default to allowed.

When all applicable sessions are disabled for the current hour, the method
returns (False, "outside_trading_session") to block trading. Hours with no
session coverage at all (21-23) still default to allowed.
"""
import builtins
import io
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Risk:
    """Minimal risk stub — MT5Executor.__init__ only stores self.risk."""
    pass


def _make_executor():
    from Python.mt5_executor import MT5Executor
    return MT5Executor(_Risk())


def _yaml_content(symbol, sessions_dict):
    """Return YAML string for a per-symbol config with the given sessions."""
    return yaml.dump({"symbol": symbol, "trading_sessions": sessions_dict})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def config_store():
    """Dict that test cases populate with {symbol: yaml_content_string}.

    The redirect_fs fixture uses this to intercept config file reads and
    serve the test content instead of hitting the real configs/ directory.
    """
    return {}


@pytest.fixture()
def redirect_fs(config_store):
    """Patch os.path.exists and builtins.open so that config reads for
    symbols present in config_store are served from memory.

    This avoids having to write to or depend on the real configs/ directory.
    Symbols not in config_store fall through to the real filesystem, which
    means missing-config tests still work correctly.
    """
    _real_exists = os.path.exists
    _real_open = builtins.open

    def _fake_exists(path):
        for symbol in config_store:
            if path.endswith(os.path.join("configs", f"{symbol}.yaml")):
                return True
        return _real_exists(path)

    def _fake_open(path, *args, **kwargs):
        for symbol, content in config_store.items():
            if path.endswith(os.path.join("configs", f"{symbol}.yaml")):
                return io.StringIO(content)
        return _real_open(path, *args, **kwargs)

    with patch("os.path.exists", _fake_exists), \
         patch("builtins.open", _fake_open):
        yield


def _register_config(config_store, symbol, sessions_dict):
    """Add a symbol's YAML config to the in-memory store."""
    config_store[symbol] = _yaml_content(symbol, sessions_dict)


# ---------------------------------------------------------------------------
# 1. All sessions enabled — always allowed
# ---------------------------------------------------------------------------

class TestAllSessionsAllowed:
    """Symbol with all three sessions true should allow trading at any hour."""

    @pytest.mark.parametrize("utc_hour", list(range(24)))
    def test_all_sessions_true_any_hour(self, config_store, redirect_fs, utc_hour):
        _register_config(config_store, "ALLSESSIONS", {
            "asian": True,
            "london": True,
            "new_york": True,
        })
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, utc_hour, 30, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("ALLSESSIONS")
        assert ok is True, f"Hour {utc_hour} should be allowed with all sessions on, got reason={reason}"

    def test_all_sessions_true_returns_ok_reason(self, config_store, redirect_fs):
        _register_config(config_store, "ALLSESSIONS", {
            "asian": True,
            "london": True,
            "new_york": True,
        })
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("ALLSESSIONS")
        assert reason == "ok"


# ---------------------------------------------------------------------------
# 2. Missing config file — allow all sessions
# ---------------------------------------------------------------------------

class TestNoConfigAllows:
    """When no config YAML exists for a symbol, trading is always allowed."""

    @pytest.mark.parametrize("utc_hour", list(range(24)))
    def test_missing_config_any_hour(self, redirect_fs, utc_hour):
        # No config registered for NOSUCHSYMBOL — falls through to real FS
        # where the file doesn't exist => allowed.
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, utc_hour, 0, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("NOSUCHSYMBOL")
        assert ok is True, f"Hour {utc_hour} should be allowed without config"
        assert reason == "ok"

    def test_config_exists_but_no_trading_sessions_key(self, config_store, redirect_fs):
        """Config present but empty trading_sessions => all allowed."""
        config_store["NOSESSIONS"] = yaml.dump({"symbol": "NOSESSIONS"})
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("NOSESSIONS")
        assert ok is True
        assert reason == "ok"


# ---------------------------------------------------------------------------
# 3. Asian session blocked — EURUSDm blocks pure-Asian hours
# ---------------------------------------------------------------------------

class TestAsianBlocked:
    """EURUSDm config has asian: false, london: true, new_york: true.

    Hours 0-6 fall ONLY in the Asian session.  With asian disabled, all
    covering sessions are disabled, so the method returns
    (False, "outside_trading_session").
    """

    @pytest.fixture(autouse=True)
    def _setup_eurusd(self, config_store):
        _register_config(config_store, "EURUSDm", {
            "asian": False,
            "london": True,
            "new_york": True,
        })

    @pytest.mark.parametrize("utc_hour", [0, 1, 2, 3, 4, 5, 6])
    def test_asian_only_hours_allowed_due_to_empty_matching_sessions(
        self, config_store, redirect_fs, utc_hour
    ):
        """Hours 0-6 are Asian-only with asian=false.

        The only covering session is disabled, so trading is blocked.
        """
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, utc_hour, 30, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("EURUSDm")
        assert ok is False, (
            f"Hour {utc_hour}: with asian=false, the only covering session is disabled, "
            f"so method should return (False, ...)"
        )

    def test_asian_london_overlap_hour_7(self, config_store, redirect_fs):
        """Hour 7 overlaps Asian + London.  London=true => allowed."""
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, 7, 30, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("EURUSDm")
        assert ok is True, "Hour 7 overlaps London (enabled), should be allowed"

    @pytest.mark.parametrize("utc_hour", [8, 9, 10, 11])
    def test_london_only_hours_allowed(self, config_store, redirect_fs, utc_hour):
        """Hours 8-11 are London-only with London enabled => allowed."""
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, utc_hour, 0, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("EURUSDm")
        assert ok is True

    @pytest.mark.parametrize("utc_hour", [12, 13, 14, 15])
    def test_london_ny_overlap_hours_allowed(self, config_store, redirect_fs, utc_hour):
        """Hours 12-15 overlap London + NY, both enabled => allowed."""
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, utc_hour, 0, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("EURUSDm")
        assert ok is True


# ---------------------------------------------------------------------------
# 4. Overlap hours — Asian/London (07:00-08:00)
# ---------------------------------------------------------------------------

class TestOverlapAsianLondon:
    """During 07-08 UTC, both Asian and London overlap.

    If either is enabled, trading is allowed.  If BOTH are disabled,
    the method returns (False, "outside_trading_session").
    """

    @pytest.mark.parametrize("asian,london,expected", [
        (False, True, True),   # London alone allows
        (True, False, True),   # Asian alone allows
        (True, True, True),    # Both enabled => allowed
        # Both disabled => blocked
        (False, False, False),
    ])
    def test_hour_7_overlap_combinations(self, config_store, redirect_fs,
                                          asian, london, expected):
        _register_config(config_store, "OVERLAPTEST", {
            "asian": asian,
            "london": london,
            "new_york": False,
        })
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, 7, 30, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, _ = executor._check_session_filter("OVERLAPTEST")
        assert ok is expected, (
            f"Hour 7 with asian={asian}, london={london} => expected allowed={expected}"
        )


# ---------------------------------------------------------------------------
# 5. Overlap hours — London/New York (12:00-16:00)
# ---------------------------------------------------------------------------

class TestOverlapLondonNY:
    """During 12-16 UTC, both London and NY overlap.

    If either is enabled, trading is allowed.  If BOTH are disabled,
    the method returns (False, "outside_trading_session").
    """

    @pytest.mark.parametrize("london,ny,expected", [
        (False, True, True),   # NY alone allows
        (True, False, True),   # London alone allows
        (True, True, True),    # Both enabled => allowed
        # Both disabled => blocked
        (False, False, False),
    ])
    @pytest.mark.parametrize("utc_hour", [12, 13, 14, 15])
    def test_london_ny_overlap_combinations(self, config_store, redirect_fs,
                                             london, ny, expected, utc_hour):
        _register_config(config_store, "LNTEST", {
            "asian": False,
            "london": london,
            "new_york": ny,
        })
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, utc_hour, 30, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, _ = executor._check_session_filter("LNTEST")
        assert ok is expected, (
            f"Hour {utc_hour} with london={london}, ny={ny} => expected allowed={expected}"
        )


# ---------------------------------------------------------------------------
# 6. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Boundary hours, gap hours, missing session keys, and error handling."""

    def test_hour_21_to_23_no_session_coverage_is_allowed(self, config_store, redirect_fs):
        """Hours 21-23 are not in any session range.  The method treats
        'no matching sessions' as allowed."""
        _register_config(config_store, "EDGE", {
            "asian": False,
            "london": False,
            "new_york": False,
        })
        executor = _make_executor()
        for hour in [21, 22, 23]:
            fake_now = datetime(2026, 1, 1, hour, 0, tzinfo=timezone.utc)
            with patch("Python.mt5_executor.datetime") as mock_dt:
                mock_dt.now.return_value = fake_now
                ok, reason = executor._check_session_filter("EDGE")
            assert ok is True, f"Hour {hour} has no session coverage and should default to allowed"
            assert reason == "ok"

    def test_session_boundary_hour_8(self, config_store, redirect_fs):
        """Hour 8 falls in London (7-16) but NOT in Asian (0-8).
        With asian=False, london=True => allowed."""
        _register_config(config_store, "BOUND", {
            "asian": False,
            "london": True,
            "new_york": False,
        })
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("BOUND")
        assert ok is True, "Hour 8 is London-only, london=True => allowed"

    def test_session_boundary_hour_16(self, config_store, redirect_fs):
        """Hour 16 falls in NY (12-21) but NOT in London (7-16).
        With london=False, new_york=True => allowed."""
        _register_config(config_store, "BOUND2", {
            "asian": False,
            "london": False,
            "new_york": True,
        })
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("BOUND2")
        assert ok is True, "Hour 16 is NY-only, ny=True => allowed"

    def test_all_sessions_false_hours_0_to_6_blocked(
        self, config_store, redirect_fs
    ):
        """With all sessions false, hours 0-6 are covered only by Asian.

        All covering sessions are disabled, so the method blocks trading.
        """
        _register_config(config_store, "ALLFALSE", {
            "asian": False,
            "london": False,
            "new_york": False,
        })
        executor = _make_executor()
        for hour in range(0, 7):
            fake_now = datetime(2026, 1, 1, hour, 0, tzinfo=timezone.utc)
            with patch("Python.mt5_executor.datetime") as mock_dt:
                mock_dt.now.return_value = fake_now
                ok, reason = executor._check_session_filter("ALLFALSE")
            assert ok is False, (
                f"Hour {hour}: all covering sessions disabled => method should block"
            )

    def test_missing_session_key_defaults_to_true(self, config_store, redirect_fs):
        """If the YAML omits a session key entirely, .get(key, True) defaults
        to True, so trading should still be allowed."""
        config_store["PARTIAL"] = yaml.dump({
            "symbol": "PARTIAL",
            "trading_sessions": {"asian": False},
        })
        executor = _make_executor()
        # Hour 10 is London-only; london key missing => defaults True => allowed
        fake_now = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("PARTIAL")
        assert ok is True, "Missing london key defaults to True => hour 10 should be allowed"

    def test_exception_during_config_read_returns_ok(self, config_store, redirect_fs):
        """If an exception occurs (e.g., bad YAML), the method catches it
        and returns (True, 'ok') to avoid blocking all trading."""
        config_store["BROKEN"] = "{{invalid yaml !!"
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("BROKEN")
        assert ok is True, "Exception during config load should not block trading"
        assert reason == "ok"

    def test_all_sessions_false_blocks_covered_hours_allows_gap_hours(
        self, config_store, redirect_fs
    ):
        """With all sessions disabled, hours covered by any session are blocked.
        Hours 21-23 have no session coverage and default to allowed.
        """
        _register_config(config_store, "NEVERBLOCK", {
            "asian": False,
            "london": False,
            "new_york": False,
        })
        executor = _make_executor()
        for hour in range(24):
            fake_now = datetime(2026, 1, 1, hour, 0, tzinfo=timezone.utc)
            with patch("Python.mt5_executor.datetime") as mock_dt:
                mock_dt.now.return_value = fake_now
                ok, reason = executor._check_session_filter("NEVERBLOCK")
            if hour <= 20:
                assert ok is False, (
                    f"Hour {hour}: all sessions disabled but method returned "
                    f"ok=True, reason={reason}"
                )
            else:
                assert ok is True, (
                    f"Hour {hour}: no session coverage should default to allowed"
                )


# ---------------------------------------------------------------------------
# 7. Positive session enforcement — verifies blocking actually works
#    when at least one session is enabled for some hours but not others
# ---------------------------------------------------------------------------

class TestPositiveSessionEnforcement:
    """Verify that the method CAN return (False, ...) when the session
    filter is configured to allow only specific sessions, and the current
    hour falls in a session range that has no enabled overlap.

    NOTE: Under the current implementation, this is actually IMPOSSIBLE.
    See the bug analysis in the module docstring: when all applicable
    sessions are disabled, matching_sessions is empty and the method
    returns (True, "ok").  These tests document the DESIRED behavior
    that the method SHOULD have.
    """

    def test_asian_disabled_blocks_pure_asian_hours(self, config_store, redirect_fs):
        """Hour 3 with only Asian coverage and asian=False should block trading.

        The implementation now correctly returns (False, "outside_trading_session").
        """
        _register_config(config_store, "DESIRED_BEHAV", {
            "asian": False,
            "london": True,
            "new_york": True,
        })
        executor = _make_executor()
        fake_now = datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
        with patch("Python.mt5_executor.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            ok, reason = executor._check_session_filter("DESIRED_BEHAV")
        assert ok is False, (
            "Hour 3 with asian=False should return False because the only "
            "covering session is disabled."
        )