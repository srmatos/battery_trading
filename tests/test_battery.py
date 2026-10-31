"""Unit tests for the physical battery model: energy accounting, losses and clipping."""
import pytest

from battery_trading.battery import Battery
from battery_trading.types import Direction
from tests.factories import make_spec


def test_charge_without_losses_stores_full_energy():
    """Lossless charging stores exactly power x duration."""
    battery = Battery(spec=make_spec(), soc_mwh=0.0)
    assert battery.apply(Direction.CHARGE, 2.0, 1.0) == pytest.approx(2.0)
    assert battery.soc_mwh == pytest.approx(2.0)


def test_discharge_matches_worked_example_in_brief():
    """5 MW for 0.5 h at 50 £/MWh is paid £125, as stated in the exercise."""
    battery = Battery(spec=make_spec(max_discharge_mw=5.0, max_storage_mwh=10.0), soc_mwh=10.0)
    realised = battery.apply(Direction.DISCHARGE, 5.0, 0.5)
    assert realised * 0.5 * 50 == pytest.approx(125.0)


def test_charge_efficiency_loss_reduces_stored_energy():
    """Importing 2 MWh with a 5% charge loss stores 1.9 MWh."""
    battery = Battery(spec=make_spec(charge_efficiency_loss=0.05), soc_mwh=0.0)
    battery.apply(Direction.CHARGE, 2.0, 1.0)
    assert battery.soc_mwh == pytest.approx(1.9)


def test_discharge_efficiency_loss_requires_more_withdrawal_than_delivered():
    """Delivering 2 MWh with a 5% discharge loss withdraws 2 / 0.95 MWh from storage."""
    battery = Battery(spec=make_spec(discharge_efficiency_loss=0.05), soc_mwh=4.0)
    assert battery.apply(Direction.DISCHARGE, 2.0, 1.0) == pytest.approx(2.0)
    assert battery.soc_mwh == pytest.approx(4.0 - 2.0 / 0.95)


def test_charge_clips_to_remaining_headroom():
    """Only the free capacity can be filled; the realised power reflects the clip."""
    battery = Battery(spec=make_spec(), soc_mwh=3.0)
    assert battery.apply(Direction.CHARGE, 2.0, 1.0) == pytest.approx(1.0)
    assert battery.soc_mwh == pytest.approx(4.0)


def test_discharge_clips_to_available_energy():
    """The battery cannot export more energy than it holds."""
    battery = Battery(spec=make_spec(), soc_mwh=1.0)
    assert battery.apply(Direction.DISCHARGE, 2.0, 1.0) == pytest.approx(1.0)
    assert battery.soc_mwh == pytest.approx(0.0)


def test_charge_clips_to_max_rate():
    """Requested power above the rate limit is capped to the rate limit."""
    battery = Battery(spec=make_spec(max_storage_mwh=100.0), soc_mwh=0.0)
    assert battery.apply(Direction.CHARGE, 10.0, 1.0) == pytest.approx(2.0)


def test_idle_is_a_no_op():
    """Idle never moves energy, whatever power is passed."""
    battery = Battery(spec=make_spec(), soc_mwh=2.0)
    assert battery.apply(Direction.IDLE, 5.0, 1.0) == 0.0
    assert battery.soc_mwh == pytest.approx(2.0)


def test_equivalent_full_cycles_tracks_discharge_throughput():
    """Withdrawing half the capacity counts as half a cycle."""
    battery = Battery(spec=make_spec(), soc_mwh=4.0)
    battery.apply(Direction.DISCHARGE, 2.0, 1.0)
    assert battery.equivalent_full_cycles == pytest.approx(0.5)
