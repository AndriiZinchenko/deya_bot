"""Time of Use state and switching.

The cloud endpoint `config/tou` returns a stale `touAction`, so the real state is read
from the inverter: holding register 146, bit 0 = Time of Use enabled, bits 1-7 = weekdays.
(Verified on a Deye hybrid: 0x00FF while on, 0x0000 / 0x00FE while off.)
"""
import time
from dataclasses import dataclass

from .deye import DeyeError

TOU_REGISTER = 146


@dataclass(frozen=True)
class TouState:
    on: bool
    raw: int

    def __str__(self):
        return "ON" if self.on else "OFF"


def read_state(client, device_sn: str) -> TouState:
    raw = client.read_holding(device_sn, TOU_REGISTER, 1)[0]
    return TouState(on=bool(raw & 1), raw=raw)


def set_state(client, device_sn: str, on: bool, settle_timeout=30.0, poll=2.0) -> TouState:
    """Switch Time of Use and confirm by reading the register back.

    Raises DeyeError if the order fails or the inverter does not report the new state.
    """
    client.switch_tou(device_sn, on)
    deadline = time.time() + settle_timeout
    while True:
        state = read_state(client, device_sn)
        if state.on == on:
            return state
        if time.time() >= deadline:
            raise DeyeError(f"order succeeded but inverter still reports Time of Use {state} (reg={state.raw:#06x})")
        time.sleep(poll)
