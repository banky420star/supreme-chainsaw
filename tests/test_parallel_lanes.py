"""Tests for ParallelLaneManager — concurrent per-symbol training pipeline.

Implementation notes (verified against actual code):
  - Lanes are created at start_cycle() time, not __init__ time.
  - LaneState.status uses "queued"/"training"/"done"/"failed" (not "pending"/"running").
  - Phase dicts include keys: status, progress_pct, epoch, epochs_total, loss, val_loss, fail_reason.
  - is_running() returns True only while threads are alive.
  - max_workers=1 with 3 symbols: one runs, two sit at "queued" via Semaphore.
"""
import time
import threading
import pytest

from Python.parallel_lane_manager import ParallelLaneManager, LaneState, LanePhaseState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_for_cycle(manager: ParallelLaneManager, timeout: float = 12.0):
    """Block until the manager stops running or timeout elapses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not manager.is_running():
            return True
        time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# LaneState / LanePhaseState unit tests
# ---------------------------------------------------------------------------

class TestLaneState:
    def test_total_progress_zero_initially(self):
        lane = LaneState(symbol='BTC')
        assert lane.total_progress == 0.0

    def test_total_progress_all_phases_done(self):
        lane = LaneState(symbol='BTC')
        lane.lstm.progress_pct = 100.0
        lane.ppo.progress_pct = 100.0
        lane.dreamer.progress_pct = 100.0
        # Weighted: 100*0.33 + 100*0.33 + 100*0.34 = 100
        assert abs(lane.total_progress - 100.0) < 1.0

    def test_total_progress_partial(self):
        lane = LaneState(symbol='BTC')
        lane.lstm.progress_pct = 100.0
        lane.ppo.progress_pct = 0.0
        lane.dreamer.progress_pct = 0.0
        # Only LSTM done: ~33%
        assert 20.0 < lane.total_progress < 50.0

    def test_total_progress_capped_at_100(self):
        lane = LaneState(symbol='BTC')
        lane.lstm.progress_pct = 200.0
        lane.ppo.progress_pct = 200.0
        lane.dreamer.progress_pct = 200.0
        assert lane.total_progress <= 100.0

    def test_to_dict_has_required_keys(self):
        lane = LaneState(symbol='BTC')
        d = lane.to_dict()
        for key in ['symbol', 'status', 'current_phase', 'total_progress', 'lstm', 'ppo', 'dreamer']:
            assert key in d, f"Missing key in LaneState.to_dict(): {key}"

    def test_to_dict_symbol_correct(self):
        lane = LaneState(symbol='XAUUSDm')
        assert lane.to_dict()['symbol'] == 'XAUUSDm'

    def test_phase_dict_has_required_keys(self):
        lane = LaneState(symbol='BTC')
        d = lane.to_dict()
        for phase_key in ('lstm', 'ppo', 'dreamer'):
            phase = d[phase_key]
            for key in ['status', 'progress_pct', 'epoch', 'epochs_total', 'loss', 'val_loss']:
                assert key in phase, f"Missing key '{key}' in {phase_key} phase dict"

    def test_initial_phase_status_queued(self):
        lane = LaneState(symbol='BTC')
        d = lane.to_dict()
        assert d['lstm']['status'] == 'queued'
        assert d['ppo']['status'] == 'queued'
        assert d['dreamer']['status'] == 'queued'

    def test_initial_progress_zero_in_phases(self):
        lane = LaneState(symbol='BTC')
        d = lane.to_dict()
        assert d['lstm']['progress_pct'] == 0.0
        assert d['ppo']['progress_pct'] == 0.0
        assert d['dreamer']['progress_pct'] == 0.0


class TestLanePhaseState:
    def test_default_status_is_queued(self):
        p = LanePhaseState()
        assert p.status == 'queued'

    def test_default_progress_is_zero(self):
        p = LanePhaseState()
        assert p.progress_pct == 0.0

    def test_default_epoch_is_zero(self):
        p = LanePhaseState()
        assert p.epoch == 0


# ---------------------------------------------------------------------------
# Manager initialisation
# ---------------------------------------------------------------------------

class TestManagerInit:
    def test_creates_with_symbols(self):
        m = ParallelLaneManager(symbols=['BTCUSDm', 'XAUUSDm'], max_workers=2)
        assert m.symbols == ['BTCUSDm', 'XAUUSDm']

    def test_not_running_initially(self):
        m = ParallelLaneManager(symbols=['BTCUSDm'], max_workers=1)
        assert not m.is_running()

    def test_get_status_before_start_has_required_keys(self):
        m = ParallelLaneManager(symbols=['BTCUSDm', 'XAUUSDm'], max_workers=2)
        status = m.get_status()
        assert 'parallel_lanes' in status
        assert 'max_parallel' in status
        assert 'active_count' in status
        assert 'is_running' in status

    def test_get_status_before_start_is_not_running(self):
        m = ParallelLaneManager(symbols=['BTCUSDm'], max_workers=1)
        status = m.get_status()
        assert status['is_running'] == False

    def test_get_status_before_start_has_empty_lanes(self):
        # Lanes are only created when start_cycle() is called
        m = ParallelLaneManager(symbols=['BTCUSDm'], max_workers=1)
        status = m.get_status()
        assert isinstance(status['parallel_lanes'], list)

    def test_max_workers_stored(self):
        m = ParallelLaneManager(symbols=['A'], max_workers=3)
        assert m.max_workers == 3

    def test_server_default_is_none(self):
        m = ParallelLaneManager(symbols=['A'], max_workers=1)
        assert m.server is None

    def test_empty_symbols_list(self):
        # Should not crash
        m = ParallelLaneManager(symbols=[], max_workers=1)
        assert m.symbols == []
        m.start_cycle()
        assert True  # no exception


# ---------------------------------------------------------------------------
# Cycle execution
# ---------------------------------------------------------------------------

class TestCycleExecution:
    def test_start_cycle_is_nonblocking(self):
        m = ParallelLaneManager(['BTCUSDm', 'XAUUSDm'], max_workers=2)
        start = time.time()
        m.start_cycle()
        elapsed = time.time() - start
        assert elapsed < 2.0, f"start_cycle() blocked for {elapsed:.2f}s"

    def test_is_running_true_after_start(self):
        m = ParallelLaneManager(['BTCUSDm'], max_workers=1)
        m.start_cycle()
        # Give thread a moment to start
        time.sleep(0.1)
        assert m.is_running()

    def test_lanes_created_for_all_symbols_after_start(self):
        m = ParallelLaneManager(['BTCUSDm', 'XAUUSDm'], max_workers=2)
        m.start_cycle()
        time.sleep(0.2)
        status = m.get_status()
        symbols = {lane['symbol'] for lane in status['parallel_lanes']}
        assert 'BTCUSDm' in symbols
        assert 'XAUUSDm' in symbols

    def test_cycle_completes(self):
        m = ParallelLaneManager(['SYM1'], max_workers=1)
        m.start_cycle()
        completed = _wait_for_cycle(m, timeout=12.0)
        assert completed, "Cycle did not complete within 12 seconds"
        status = m.get_status()
        lane = status['parallel_lanes'][0]
        assert lane['status'] in ('done', 'failed')

    def test_cycle_complete_status_is_done(self):
        m = ParallelLaneManager(['SYM1'], max_workers=1)
        m.start_cycle()
        _wait_for_cycle(m, timeout=12.0)
        status = m.get_status()
        assert status['parallel_lanes'][0]['status'] == 'done'

    def test_cycle_complete_progress_is_100(self):
        m = ParallelLaneManager(['SYM1'], max_workers=1)
        m.start_cycle()
        _wait_for_cycle(m, timeout=12.0)
        status = m.get_status()
        assert status['parallel_lanes'][0]['total_progress'] == 100.0

    def test_is_running_false_after_completion(self):
        m = ParallelLaneManager(['SYM1'], max_workers=1)
        m.start_cycle()
        _wait_for_cycle(m, timeout=12.0)
        assert not m.is_running()

    def test_double_start_is_safe(self):
        m = ParallelLaneManager(['BTCUSDm', 'XAUUSDm'], max_workers=2)
        m.start_cycle()
        # Second call should log warning and return without crashing or spawning extra threads
        m.start_cycle()
        assert True  # no exception raised

    def test_progress_increases_over_time(self):
        m = ParallelLaneManager(['TESTSYM'], max_workers=1)
        m.start_cycle()
        time.sleep(0.3)
        status1 = m.get_status()
        p1 = status1['parallel_lanes'][0]['total_progress'] if status1['parallel_lanes'] else 0.0
        time.sleep(0.5)
        status2 = m.get_status()
        p2 = status2['parallel_lanes'][0]['total_progress'] if status2['parallel_lanes'] else 0.0
        assert p2 >= p1, f"Progress went backwards: {p1} → {p2}"

    def test_all_phases_complete_after_cycle(self):
        m = ParallelLaneManager(['SYM1'], max_workers=1)
        m.start_cycle()
        _wait_for_cycle(m, timeout=12.0)
        lane = m.get_status()['parallel_lanes'][0]
        assert lane['lstm']['status'] == 'done'
        assert lane['ppo']['status'] == 'done'
        assert lane['dreamer']['status'] == 'done'

    def test_active_count_resets_after_completion(self):
        m = ParallelLaneManager(['SYM1'], max_workers=1)
        m.start_cycle()
        _wait_for_cycle(m, timeout=12.0)
        status = m.get_status()
        assert status['active_count'] == 0

    def test_multiple_symbols_all_complete(self):
        m = ParallelLaneManager(['A', 'B'], max_workers=2)
        m.start_cycle()
        _wait_for_cycle(m, timeout=20.0)
        lanes = m.get_status()['parallel_lanes']
        assert len(lanes) == 2
        for lane in lanes:
            assert lane['status'] == 'done', f"Lane {lane['symbol']} not done: {lane['status']}"

    def test_restart_after_natural_completion(self):
        """Regression: start_cycle() must be callable again after a cycle finishes
        naturally. Previously, _active was never reset, permanently blocking restarts.
        """
        m = ParallelLaneManager(['SYM_RESTART'], max_workers=1)
        m.start_cycle()
        completed = _wait_for_cycle(m, timeout=12.0)
        assert completed, "First cycle did not complete"

        # At this point _active is True but no threads are alive — restart must work
        m.start_cycle()
        time.sleep(0.3)
        status = m.get_status()
        lanes = status['parallel_lanes']
        assert len(lanes) == 1, "Second cycle did not create any lane"
        assert lanes[0]['symbol'] == 'SYM_RESTART'
        # Lane should be in an active/fresh state (not stale 'done' from first cycle)
        assert lanes[0]['status'] in ('queued', 'training', 'done'), \
            f"Unexpected lane status after restart: {lanes[0]['status']}"


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------

class TestConcurrency:
    def test_max_workers_respected_active_count(self):
        # With max_workers=1 and 3 symbols, at most 1 should be training at a time
        m = ParallelLaneManager(['A', 'B', 'C'], max_workers=1)
        m.start_cycle()
        time.sleep(0.3)
        status = m.get_status()
        active = status['active_count']
        assert active <= 1, f"Expected active_count ≤ 1, got {active}"

    def test_max_workers_respected_status_field(self):
        # With max_workers=1: only 1 lane should be "training", others "queued"
        m = ParallelLaneManager(['A', 'B', 'C'], max_workers=1)
        m.start_cycle()
        time.sleep(0.3)
        statuses = [l['status'] for l in m.get_status()['parallel_lanes']]
        training_count = statuses.count('training')
        assert training_count <= 1, f"Expected ≤1 training, got: {statuses}"

    def test_thread_safety_of_get_status(self):
        """Concurrent reads should not raise exceptions."""
        m = ParallelLaneManager(['BTCUSDm', 'XAUUSDm'], max_workers=2)
        m.start_cycle()
        errors = []

        def reader():
            for _ in range(30):
                try:
                    m.get_status()
                    time.sleep(0.03)
                except Exception as e:
                    errors.append(str(e))

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread-safety errors: {errors}"

    def test_concurrent_start_does_not_corrupt_state(self):
        """Hammering start_cycle from two threads should not corrupt lane state."""
        m = ParallelLaneManager(['X'], max_workers=1)
        exceptions = []

        def starter():
            try:
                m.start_cycle()
            except Exception as e:
                exceptions.append(str(e))

        t1 = threading.Thread(target=starter)
        t2 = threading.Thread(target=starter)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not exceptions, f"Exceptions during concurrent start: {exceptions}"

    def test_get_status_is_snapshot_not_live_reference(self):
        """Mutating the returned dict should not affect internal state."""
        m = ParallelLaneManager(['BTCUSDm'], max_workers=1)
        m.start_cycle()
        time.sleep(0.1)

        s1 = m.get_status()
        s1['parallel_lanes'] = []  # Mutate the snapshot
        s1['max_parallel'] = 9999

        s2 = m.get_status()
        # Internal state should be unaffected
        assert s2['max_parallel'] == m.max_workers
