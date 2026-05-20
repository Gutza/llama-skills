"""Environment-based configuration for llama-skills."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings loaded from environment variables."""

    skills_dir: str
    backend: str
    host: str
    port: int
    public_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        skills_dir = os.environ.get("LLAMA_SKILLS_DIR")
        if not skills_dir:
            msg = "LLAMA_SKILLS_DIR environment variable is required"
            raise ValueError(msg)

        public_url = os.environ.get("LLAMA_SKILLS_PUBLIC_URL")
        if public_url:
            public_url = public_url.rstrip("/")

        return cls(
            skills_dir=skills_dir,
            backend=os.environ.get(
                "LLAMA_SKILLS_BACKEND", "http://localhost:8080"
            ).rstrip("/"),
            host=os.environ.get("LLAMA_SKILLS_HOST", "0.0.0.0"),
            port=int(os.environ.get("LLAMA_SKILLS_PORT", "8081")),
            public_url=public_url,
        )
