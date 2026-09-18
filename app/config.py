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
    model_timeout: float = float(os.getenv('MODEL_TIMEOUT', '90'))
    model_json_mode: bool = os.getenv('MODEL_JSON_MODE', 'true').lower() == 'true'
    secure_cookie: bool = os.getenv('SECURE_COOKIE', 'false').lower() == 'true'
    max_upload: int = 10 * 1024 * 1024

    @property
    def configured(self):
        return bool(self.model_base_url and self.model_name and (self.model_mode == 'local' or self.model_api_key))
