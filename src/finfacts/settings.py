"""Runtime settings, read only from environment variables (or a local, gitignored .env)."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sec_user_agent: str = Field(description="App name + contact email, required by SEC.")
    sec_max_rps: float = Field(default=8.0, gt=0, le=10)
    data_dir: Path = Path("data")

    @field_validator("sec_user_agent")
    @classmethod
    def _must_have_contact(cls, v: str) -> str:
        # SEC blocks requests without a contact address in the User-Agent.
        if "@" not in v or " " not in v.strip():
            raise ValueError("SEC_USER_AGENT must look like 'AppName/1.0 you@example.com'")
        return v.strip()

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def flat_dir(self) -> Path:
        return self.data_dir / "flat"

    @property
    def state_path(self) -> Path:
        return self.data_dir / "ops" / "ingest_state.json"
