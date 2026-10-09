# deya_bot

Telegram bot for a Deye hybrid inverter (DeyeCloud Open API).

| Command | What it does |
|---|---|
| `/tou` | Shows the **real** Time of Use state with a one-tap ON/OFF button. After a switch it reads the inverter back and only then says "confirmed". |
| `/status` | PV, load, grid and battery SOC/power right now. |
| `/chart [hours]` | PNG dashboard from the local SQLite history (default 24 h). |

Only `TELEGRAM_USER_ID` may use the bot; everyone else is ignored silently.

## Run

```sh
pip install -r requirements.txt
cp .env.example .env      # fill in the values; never commit .env
python -m deye_bot
```

Credentials come from environment variables (or `.env`). You need an app from
<https://developer.deyecloud.com> (`appId`, `appSecret`) plus your DeyeCloud account
email and password. The password is sent as a SHA-256 digest; set
`DEYE_PASSWORD_IS_SHA256=1` if you put an already-hashed value in `DEYE_PASSWORD`.
A background job stores a sample every `POLL_MINUTES` for the charts.

## How Time of Use is read and switched

* `POST /v1.0/config/tou` reports a **stale** `touAction` (it was wrong twice during
  testing), so the bot does not use it.
* State is read from the inverter itself: Modbus holding register 146 through
  `POST /v1.0/order/customControl`. Bit 0 = Time of Use enabled, bits 1–7 = weekdays
  (`0x00FF` on, `0x0000`/`0x00FE` off).
* Switching uses `POST /v1.0/order/sys/tou/switch` (all seven days when turning on),
  waits for the order (`GET /v1.0/order/{id}`, status 666 = done), then re-reads register 146.
* The six slots are not touched.

Cloud round trips are slow (seconds to tens of seconds); the bot shows "Switching…" meanwhile.

## Sign conventions

Grid: `+` importing, `−` exporting. Battery: `+` discharging, `−` charging.

## Tests

```sh
python -m pytest
```
The HTTP layer is tested against a fake session, and the Modbus parser against replies
captured from a real inverter.
