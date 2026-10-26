import os
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Automatically load .env from project root
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

class SystemSettings(BaseModel):
    # LLM Configuration
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    ollama_base_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    default_llm_provider: str = Field(default_factory=lambda: os.getenv("DEFAULT_LLM_PROVIDER", "auto"))
    default_model: str = Field(default_factory=lambda: os.getenv("DEFAULT_MODEL", "gemini-2.5-flash"))

    # Browser Automation
    browser_headless: bool = Field(default_factory=lambda: os.getenv("BROWSER_HEADLESS", "false").lower() == "true")
    browser_stealth: bool = Field(default_factory=lambda: os.getenv("BROWSER_STEALTH", "false").lower() == "true")
    browser_viewport_width: int = Field(default_factory=lambda: int(os.getenv("BROWSER_VIEWPORT_WIDTH", "1280")))
    browser_viewport_height: int = Field(default_factory=lambda: int(os.getenv("BROWSER_VIEWPORT_HEIGHT", "800")))
    user_data_dir: Path = Field(default_factory=lambda: ROOT_DIR / "data" / "browser_profiles")

    # Mobile Automation
    adb_enabled: bool = Field(default_factory=lambda: os.getenv("ADB_ENABLED", "true").lower() == "true")
    adb_device_id: str = Field(default_factory=lambda: os.getenv("ADB_DEVICE_ID", ""))
    adb_host: str = Field(default_factory=lambda: os.getenv("ADB_HOST", "127.0.0.1"))
    adb_port: int = Field(default_factory=lambda: int(os.getenv("ADB_PORT", "5037")))

    # Desktop Automation
    desktop_safety_failsafe: bool = Field(default_factory=lambda: os.getenv("DESKTOP_SAFETY_FAILSAFE", "true").lower() == "true")
    desktop_action_pause: float = Field(default_factory=lambda: float(os.getenv("DESKTOP_ACTION_PAUSE", "0.2")))

    # Server & Mission Control
    server_host: str = Field(default_factory=lambda: os.getenv("SERVER_HOST", "127.0.0.1"))
    server_port: int = Field(default_factory=lambda: int(os.getenv("SERVER_PORT", "8000")))
    auth_password: str = Field(default_factory=lambda: os.getenv("NOVA_APEX_AUTH_PASSWORD", ""))
    auth_cookie_secure: bool = Field(default_factory=lambda: os.getenv("NOVA_APEX_COOKIE_SECURE", "true").lower() == "true")
    auth_session_ttl_seconds: int = Field(default_factory=lambda: int(os.getenv("NOVA_APEX_SESSION_TTL_SECONDS", "28800")))
    workspace_dir: Path = Field(default_factory=lambda: Path(os.getenv("WORKSPACE_DIR", str(ROOT_DIR / "workspace"))))
    artifacts_dir: Path = Field(default_factory=lambda: ROOT_DIR / "data" / "artifacts")
    session_logs_dir: Path = Field(default_factory=lambda: ROOT_DIR / "data" / "logs")

settings = SystemSettings()

# Ensure directories exist
settings.workspace_dir.mkdir(parents=True, exist_ok=True)
settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
settings.session_logs_dir.mkdir(parents=True, exist_ok=True)
settings.user_data_dir.mkdir(parents=True, exist_ok=True)
