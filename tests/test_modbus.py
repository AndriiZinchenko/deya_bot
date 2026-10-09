import pytest

from deye_bot.modbus import ModbusError, crc16, parse_read_response, read_holding_frame


def test_crc_standard_vector():
    assert read_holding_frame(0, 10) == "01030000000AC5CD"


def test_frame_for_tou_register_matches_the_one_sent_to_the_inverter():
    assert read_holding_frame(146, 1) == "01030092000125E7"
    assert read_holding_frame(148, 30) == "01030094001E842E"


# Replies captured from the real inverter during the toggle test.
@pytest.mark.parametrize("reply,value", [("01030200FE39C4", 0x00FE), ("01030200FFF804", 0x00FF),
                                         ("0103020000B844", 0x0000)])
def test_parse_real_replies(reply, value):
    assert parse_read_response(reply, 1) == [value]


def test_parse_slot_block():
    reply = ("01033C006401F40384051406A40834177017701770177017701770132413241324132413241324"
             "0028002800410041003200320001000100000000000100015F6B")
    regs = parse_read_response(reply, 30)
    assert regs[:6] == [100, 500, 900, 1300, 1700, 2100]  # 01:00 05:00 09:00 13:00 17:00 21:00
    assert regs[6:12] == [6000] * 6


def test_bad_crc_rejected():
    with pytest.raises(ModbusError, match="CRC"):
        parse_read_response("01030200FE39C5", 1)


def test_exception_reply_rejected():
    body = bytes([1, 0x83, 2])
    crc = crc16(body)
    with pytest.raises(ModbusError, match="exception"):
        parse_read_response((body + bytes([crc & 255, crc >> 8])).hex(), 1)


def test_wrong_quantity_rejected():
    with pytest.raises(ModbusError):
        parse_read_response("01030200FE39C4", 2)
