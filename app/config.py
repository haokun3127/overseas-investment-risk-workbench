import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')

@dataclass
class Settings:
    data_dir: Path = Path(os.getenv('DATA_DIR', str(ROOT / 'data')))
    model_mode: str = os.getenv('MODEL_MODE', 'external')
    model_base_url: str = os.getenv('MODEL_BASE_URL', '').rstrip('/')
    model_name: str = os.getenv('MODEL_NAME', '')
    model_api_key: str = os.getenv('MODEL_API_KEY', '')
    model_wire_api: str = os.getenv('MODEL_WIRE_API', 'chat_completions')
    model_reasoning_effort: str = os.getenv('MODEL_REASONING_EFFORT', '')
    model_store: bool = os.getenv('MODEL_STORE', 'false').lower() == 'true'
    model_timeout: float = float(os.getenv('MODEL_TIMEOUT', '90'))
    model_json_mode: bool = os.getenv('MODEL_JSON_MODE', 'true').lower() == 'true'
    secure_cookie: bool = os.getenv('SECURE_COOKIE', 'false').lower() == 'true'
    cookie_path: str = os.getenv('COOKIE_PATH', '/')
    session_cookie_name: str = os.getenv('SESSION_COOKIE_NAME', 'risk_session')
    max_upload: int = 10 * 1024 * 1024

    @property
    def configured(self):
        return bool(self.model_base_url and self.model_name and self.model_mode == 'external' and self.model_api_key)
