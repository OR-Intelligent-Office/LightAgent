"""
Konfiguracja LightAgent.
Można załadować z zmiennych środowiskowych lub .env
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Config:
    """Główna konfiguracja aplikacji."""
    
    simulator_url: str = "http://localhost:8080"
    poll_interval: float = 0.5
    daylight_threshold: float = 0.3
    motion_timeout: float = 180.0
    auto_brightness: bool = True
    
    @classmethod
    def from_env(cls) -> "Config":
        """Tworzy konfigurację z zmiennych środowiskowych."""
        load_dotenv()
        
        return cls(
            simulator_url=os.getenv("SIMULATOR_URL", "http://localhost:8080"),
            poll_interval=float(os.getenv("POLL_INTERVAL", "0.5")),
            daylight_threshold=float(os.getenv("DAYLIGHT_THRESHOLD", "0.3")),
            motion_timeout=float(os.getenv("MOTION_TIMEOUT", "180")),
            auto_brightness=os.getenv("AUTO_BRIGHTNESS", "true").lower() == "true",
        )

