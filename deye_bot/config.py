import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path=".env"):
    """Tiny .env reader; real environment variables win."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass(frozen=True)
class Config:
    telegram_token: str
    telegram_user_id: int
    app_id: str
    app_secret: str
    email: str
    password: str
    data_center: str
    device_sn: str
    db_path: str
    poll_minutes: float
    timezone: str
    password_is_hashed: bool

    @classmethod
    def from_env(cls):
        env = os.environ
        required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_USER_ID", "DEYE_APP_ID", "DEYE_APP_SECRET",
                    "DEYE_EMAIL", "DEYE_PASSWORD"]
        missing = [k for k in required if not env.get(k)]
        if missing:
            raise SystemExit("Missing environment variables: " + ", ".join(missing))
        try:
            user_id = int(env["TELEGRAM_USER_ID"])
        except ValueError:
            raise SystemExit("TELEGRAM_USER_ID must be a number")
        return cls(
            telegram_token=env["TELEGRAM_BOT_TOKEN"], telegram_user_id=user_id,
            app_id=env["DEYE_APP_ID"], app_secret=env["DEYE_APP_SECRET"],
            email=env["DEYE_EMAIL"], password=env["DEYE_PASSWORD"],
            data_center=env.get("DEYE_DATA_CENTER", "eu"), device_sn=env.get("DEYE_DEVICE_SN", ""),
            db_path=env.get("DB_PATH", "deye_bot.db"),
            poll_minutes=float(env.get("POLL_MINUTES", "5")),
            timezone=env.get("TIMEZONE", "Europe/Helsinki"),
            password_is_hashed=env.get("DEYE_PASSWORD_IS_SHA256", "") == "1",
        )
