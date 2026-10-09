"""Minimal Modbus RTU helpers for the DeyeCloud `order/customControl` endpoint.

The cloud relays a raw RTU frame (hex, CRC included) to the inverter and returns the
inverter's raw reply in the order result.
"""

READ_HOLDING = 0x03


class ModbusError(Exception):
    pass


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _with_crc(body: bytes) -> bytes:
    crc = crc16(body)
    return body + bytes([crc & 0xFF, crc >> 8])


def read_holding_frame(address: int, quantity: int, slave: int = 1) -> str:
    """Hex RTU frame for 'read `quantity` holding registers from `address`'."""
    body = bytes([slave, READ_HOLDING, address >> 8, address & 0xFF, quantity >> 8, quantity & 0xFF])
    return _with_crc(body).hex().upper()


def parse_read_response(hex_reply: str, quantity: int, slave: int = 1) -> list[int]:
    """Decode a read-holding reply into `quantity` register values, verifying CRC."""
    try:
        raw = bytes.fromhex(hex_reply)
    except ValueError as exc:
        raise ModbusError(f"reply is not hex: {hex_reply!r}") from exc
    if len(raw) < 5:
        raise ModbusError(f"reply too short: {hex_reply!r}")
    if crc16(raw[:-2]) != raw[-2] | (raw[-1] << 8):
        raise ModbusError(f"bad CRC in reply {hex_reply!r}")
    if raw[0] != slave:
        raise ModbusError(f"reply from unexpected slave {raw[0]}")
    if raw[1] == READ_HOLDING | 0x80:
        raise ModbusError(f"inverter returned Modbus exception code {raw[2]}")
    if raw[1] != READ_HOLDING:
        raise ModbusError(f"unexpected function code {raw[1]:#x}")
    if raw[2] != quantity * 2 or len(raw) != 3 + raw[2] + 2:
        raise ModbusError(f"expected {quantity} registers, got reply {hex_reply!r}")
    data = raw[3:-2]
    return [(data[i] << 8) | data[i + 1] for i in range(0, len(data), 2)]
