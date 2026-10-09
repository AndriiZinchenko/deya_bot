import logging

from .bot import build
from .config import Config, load_dotenv
from .deye import DeyeClient
from .store import Store


def main():
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its URLs contain the bot token
    load_dotenv()
    cfg = Config.from_env()
    client = DeyeClient(cfg.app_id, cfg.app_secret, cfg.email, cfg.password, cfg.data_center,
                        password_is_hashed=cfg.password_is_hashed)
    build(cfg, client, Store(cfg.db_path)).run_polling()


if __name__ == "__main__":
    main()
