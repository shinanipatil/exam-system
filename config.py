import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "online_exam")

    AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "").strip()
    AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID", "").strip()
    AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET", "").strip()

    _AUTH0_PLACEHOLDERS = {
        "your-tenant.us.auth0.com",
        "your_client_id",
        "your_client_secret",
    }

    @property
    def auth0_enabled(self):
        if not (self.AUTH0_DOMAIN and self.AUTH0_CLIENT_ID and self.AUTH0_CLIENT_SECRET):
            return False
        values = {self.AUTH0_DOMAIN, self.AUTH0_CLIENT_ID, self.AUTH0_CLIENT_SECRET}
        if values & self._AUTH0_PLACEHOLDERS:
            return False
        if "your-tenant" in self.AUTH0_DOMAIN or "auth0.com" not in self.AUTH0_DOMAIN:
            return False
        return True
