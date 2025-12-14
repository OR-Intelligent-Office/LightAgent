"""
Klient HTTP do komunikacji z symulatorem budynku.
"""

import httpx
from typing import Optional
from rich.console import Console

from .models import SimulatorState, LightState

console = Console()


class SimulatorClient:
    """Klient do komunikacji z symulatorem budynku."""

    def __init__(self, base_url: str = "http://localhost:8080"):
        """
        Inicjalizacja klienta.
        
        Args:
            base_url: Bazowy URL symulatora
        """
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=10.0)

    async def get_state(self) -> Optional[SimulatorState]:
        """
        Pobiera aktualny stan symulatora.
        
        Returns:
            SimulatorState lub None w przypadku błędu
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/state")
            response.raise_for_status()
            data = response.json()
            return SimulatorState.model_validate(data)
        except httpx.HTTPStatusError as e:
            console.print(f"[red]Błąd HTTP: {e.response.status_code}[/red]")
            return None
        except httpx.RequestError as e:
            console.print(f"[red]Błąd połączenia z symulatorem: {e}[/red]")
            return None
        except Exception as e:
            console.print(f"[red]Nieoczekiwany błąd: {e}[/red]")
            return None

    async def set_light_state(
        self, 
        light_id: str, 
        state: LightState, 
        brightness: Optional[int] = None
    ) -> bool:
        """
        Ustawia stan światła.
        
        Args:
            light_id: ID światła
            state: Nowy stan (ON/OFF)
            brightness: Opcjonalna jasność (0-100)
            
        Returns:
            True jeśli sukces, False w przeciwnym wypadku
        """
        try:
            payload = {
                "lightId": light_id,
                "state": state.value
            }
            if brightness is not None:
                payload["brightness"] = brightness

            response = await self.client.post(
                f"{self.base_url}/api/lights/control",
                json=payload
            )
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            console.print(f"[red]Błąd HTTP przy sterowaniu światłem: {e.response.status_code}[/red]")
            return False
        except httpx.RequestError as e:
            console.print(f"[red]Błąd połączenia: {e}[/red]")
            return False

    async def turn_on_light(self, light_id: str, brightness: int = 100) -> bool:
        """Włącza światło."""
        return await self.set_light_state(light_id, LightState.ON, brightness)

    async def turn_off_light(self, light_id: str) -> bool:
        """Wyłącza światło."""
        return await self.set_light_state(light_id, LightState.OFF)

    async def close(self):
        """Zamyka połączenie HTTP."""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

