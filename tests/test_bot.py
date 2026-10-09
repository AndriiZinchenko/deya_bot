import asyncio
from types import SimpleNamespace as NS

from deye_bot import bot, tou
from deye_bot.config import Config
from deye_bot.deye import DeyeError, Snapshot
from deye_bot.store import Store

CFG = Config("t", 42, "a", "s", "e", "p", "eu", "SN", ":memory:", 5, "Europe/Helsinki", False)


class Msg:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kw):
        self.sent.append(text)
        return self

    async def edit_text(self, text, **kw):
        self.sent.append(text)

    async def reply_photo(self, photo, **kw):
        self.sent.append(("photo", len(photo)))


class Query(Msg):
    def __init__(self, data):
        super().__init__()
        self.data, self.answers = data, []

    async def answer(self, *a, **kw):
        self.answers.append((a, kw))

    async def edit_message_text(self, text, **kw):
        self.sent.append(text)


class FakeClient:
    def __init__(self):
        self.reg, self.fail_switch = 0x0000, False

    def read_holding(self, sn, addr, qty):
        return [self.reg]

    def switch_tou(self, sn, on):
        if self.fail_switch:
            raise DeyeError("device offline")
        self.reg = 0x00FF if on else 0x0000

    def latest(self, sn):
        return Snapshot(1_700_000_000, 419, 533, 2345, -2266, 93)


def make(tmp_path):
    return bot.App(CFG, FakeClient(), Store(str(tmp_path / "b.db")))


def run(coro):
    return asyncio.run(coro)


def upd(user_id, message=None, query=None):
    return NS(effective_user=NS(id=user_id), message=message, callback_query=query)


CTX = NS(args=[], bot_data={})


def test_stranger_is_ignored(tmp_path):
    app, msg = make(tmp_path), Msg()
    run(app.status(upd(999, message=msg), CTX))
    run(app.tou_cmd(upd(999, message=msg), CTX))
    q = Query("tou:on")
    run(app.tou_button(upd(999, query=q), CTX))
    assert msg.sent == [] and q.sent == [] and app.client.reg == 0


def test_status_text_and_it_is_recorded(tmp_path):
    app, msg = make(tmp_path), Msg()
    run(app.status(upd(42, message=msg), CTX))
    text = msg.sent[0]
    assert "PV: 0.42 kW" in text and "Grid: 2.35 kW importing" in text
    assert "Battery: 93% · 2.27 kW charging" in text
    assert len(app.store.since(10**6, now=1_700_000_000)) == 1


def test_button_switches_and_confirms(tmp_path):
    app, q = make(tmp_path), Query("tou:on")
    run(app.tou_button(upd(42, query=q), CTX))
    assert app.client.reg == 0x00FF
    assert "ON" in q.sent[-1] and "confirmed" in q.sent[-1]


def test_failed_switch_reports_real_state(tmp_path):
    app, q = make(tmp_path), Query("tou:on")
    app.client.fail_switch = True
    run(app.tou_button(upd(42, query=q), CTX))
    assert "device offline" in q.sent[-1] and "Time of Use: OFF" in q.sent[-1]


def test_chart_usage_and_no_data(tmp_path):
    app, msg = make(tmp_path), Msg()
    run(app.chart(upd(42, message=msg), NS(args=["abc"], bot_data={})))
    run(app.chart(upd(42, message=msg), NS(args=[], bot_data={})))
    assert msg.sent[0].startswith("Usage") and "Not enough data" in msg.sent[1]


def test_keyboard_offers_opposite_action():
    on = bot.tou_keyboard(tou.TouState(True, 0xFF)).inline_keyboard[0][0]
    off = bot.tou_keyboard(tou.TouState(False, 0)).inline_keyboard[0][0]
    assert (on.callback_data, off.callback_data) == ("tou:off", "tou:on")


def test_app_builds():
    app = bot.build(CFG, FakeClient(), Store(":memory:"))
    assert len(app.handlers[0]) == 5
