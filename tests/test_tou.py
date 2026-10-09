import pytest

from deye_bot import tou
from deye_bot.deye import DeyeError


class FakeInverter:
    """Mimics the register behaviour seen on the real inverter."""

    def __init__(self, reg=0x00FE, follow=True):
        self.reg, self.follow, self.switches = reg, follow, []

    def read_holding(self, sn, addr, qty):
        assert (addr, qty) == (146, 1)
        return [self.reg]

    def switch_tou(self, sn, on):
        self.switches.append(on)
        if self.follow:
            self.reg = 0x00FF if on else 0x0000


@pytest.mark.parametrize("reg,on", [(0x00FE, False), (0x0000, False), (0x00FF, True), (0x0001, True)])
def test_read_state_uses_bit0(reg, on):
    assert tou.read_state(FakeInverter(reg), "SN").on is on


def test_set_state_confirms_by_readback():
    inv = FakeInverter()
    assert tou.set_state(inv, "SN", True).on is True
    assert tou.set_state(inv, "SN", False).on is False
    assert inv.switches == [True, False]


def test_set_state_fails_loudly_when_inverter_does_not_follow(monkeypatch):
    monkeypatch.setattr(tou.time, "sleep", lambda _: None)
    with pytest.raises(DeyeError, match="still reports"):
        tou.set_state(FakeInverter(follow=False), "SN", True, settle_timeout=0)
