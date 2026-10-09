import asyncio
import functools
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from . import charts, tou
from .deye import DeyeError, Snapshot

log = logging.getLogger(__name__)
HELP = ("/tou – Time of Use state with an ON/OFF button\n"
        "/status – PV, load, grid, battery\n"
        "/chart [hours] – dashboard (default 24 h)")


def format_status(s: Snapshot, tz: str) -> str:
    grid = "importing" if s.grid_w > 0 else "exporting" if s.grid_w < 0 else "idle"
    batt = "discharging" if s.battery_w > 0 else "charging" if s.battery_w < 0 else "idle"
    when = datetime.fromtimestamp(s.ts, ZoneInfo(tz)).strftime("%H:%M")
    return (f"PV: {s.pv_w / 1000:.2f} kW\nLoad: {s.load_w / 1000:.2f} kW\n"
            f"Grid: {abs(s.grid_w) / 1000:.2f} kW {grid}\n"
            f"Battery: {s.soc:.0f}% · {abs(s.battery_w) / 1000:.2f} kW {batt}\n"
            f"Updated {when}")


def tou_keyboard(state: tou.TouState) -> InlineKeyboardMarkup:
    toggle = InlineKeyboardButton("Turn OFF" if state.on else "Turn ON", callback_data="tou:off" if state.on else "tou:on")
    return InlineKeyboardMarkup([[toggle, InlineKeyboardButton("Refresh", callback_data="tou:refresh")]])


def authorized(handler):
    """Only the configured Telegram user may use the bot; everyone else is ignored silently."""
    @functools.wraps(handler)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user is None or user.id != self.cfg.telegram_user_id:
            log.warning("ignored update from user %s", user.id if user else None)
            return
        return await handler(self, update, context)
    return wrapper


class App:
    def __init__(self, cfg, client, store):
        self.cfg, self.client, self.store = cfg, client, store
        self.device_sn = cfg.device_sn
        self.lock = asyncio.Lock()  # one inverter command at a time

    async def sn(self):
        if not self.device_sn:
            self.device_sn = await asyncio.to_thread(self.client.find_inverter)
            log.info("using inverter %s", self.device_sn)
        return self.device_sn

    async def snapshot(self) -> Snapshot:
        s = await asyncio.to_thread(self.client.latest, await self.sn())
        self.store.add(s)
        return s

    # ---- jobs -----------------------------------------------------------
    async def collect(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            await self.snapshot()
        except Exception:
            log.exception("collector failed")

    # ---- handlers -------------------------------------------------------
    @authorized
    async def start(self, update, context):
        await update.message.reply_text(HELP)

    @authorized
    async def status(self, update, context):
        try:
            s = await self.snapshot()
        except DeyeError as exc:
            return await update.message.reply_text(f"Could not read the inverter: {exc}")
        await update.message.reply_text(format_status(s, self.cfg.timezone))

    @authorized
    async def chart(self, update, context):
        try:
            hours = float(context.args[0]) if context.args else 24.0
            if not 0 < hours <= 24 * 30:
                raise ValueError
        except ValueError:
            return await update.message.reply_text("Usage: /chart [hours], 1–720")
        png = await asyncio.to_thread(charts.render, self.store.since(hours), hours, self.cfg.timezone)
        if png is None:
            return await update.message.reply_text("Not enough data yet – the collector needs a few samples.")
        await update.message.reply_photo(png)

    async def _tou_state_text(self):
        state = await asyncio.to_thread(tou.read_state, self.client, await self.sn())
        return state, f"Time of Use: {state}"

    @authorized
    async def tou_cmd(self, update, context):
        msg = await update.message.reply_text("Reading inverter…")
        try:
            state, text = await self._tou_state_text()
        except DeyeError as exc:
            return await msg.edit_text(f"Could not read Time of Use: {exc}")
        await msg.edit_text(text, reply_markup=tou_keyboard(state))

    @authorized
    async def tou_button(self, update, context):
        query = update.callback_query
        action = query.data.split(":", 1)[1]
        if self.lock.locked():
            return await query.answer("Another command is still running", show_alert=True)
        await query.answer()
        async with self.lock:
            try:
                if action in ("on", "off"):
                    await query.edit_message_text(f"Switching Time of Use {action.upper()}… (up to ~30 s)")
                    state = await asyncio.to_thread(tou.set_state, self.client, await self.sn(), action == "on")
                    text = f"Time of Use: {state} ✓ confirmed on the inverter"
                else:
                    state, text = await self._tou_state_text()
            except DeyeError as exc:
                log.warning("tou action %s failed: %s", action, exc)
                try:
                    state, text = await self._tou_state_text()
                    text = f"⚠ {exc}\n{text}"
                except DeyeError:
                    return await query.edit_message_text(f"⚠ {exc}")
        await query.edit_message_text(text, reply_markup=tou_keyboard(state))


def build(cfg, client, store) -> Application:
    app = Application.builder().token(cfg.telegram_token).build()
    app.bot_data["cfg"] = cfg
    h = App(cfg, client, store)
    app.add_handler(CommandHandler(["start", "help"], h.start))
    app.add_handler(CommandHandler("status", h.status))
    app.add_handler(CommandHandler("chart", h.chart))
    app.add_handler(CommandHandler("tou", h.tou_cmd))
    app.add_handler(CallbackQueryHandler(h.tou_button, pattern=r"^tou:(on|off|refresh)$"))
    app.job_queue.run_repeating(h.collect, interval=cfg.poll_minutes * 60, first=5)
    return app
