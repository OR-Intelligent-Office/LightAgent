#!/usr/bin/env python3
import asyncio
import aiohttp
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("LightAgent")


class SimpleLightAgent:
    """Prosty agent oświetlenia."""
    
    def __init__(self, simulator_url: str = "http://localhost:8080"):
        self.simulator_url = simulator_url
        self.session = None
        self.running = False
        
        # Konfiguracja
        self.poll_interval = 2.0  # sekundy
        self.daylight_threshold = 0.3  # próg światła dziennego
    
    async def start(self):
        """Uruchamia agenta."""
        self.session = aiohttp.ClientSession()
        self.running = True
        logger.info(f"🚀 LightAgent uruchomiony - {self.simulator_url}")
        
        try:
            while self.running:
                await self.run_cycle()
                await asyncio.sleep(self.poll_interval)
        finally:
            await self.session.close()
    
    def stop(self):
        """Zatrzymuje agenta."""
        self.running = False
        logger.info("🛑 LightAgent zatrzymany")
    
    async def get_state(self) -> dict | None:
        """Pobiera stan środowiska z symulatora."""
        try:
            async with self.session.get(f"{self.simulator_url}/api/environment/state") as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Błąd pobierania stanu: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Błąd połączenia: {e}")
            return None
    
    async def set_light(self, light_id: str, state: str, brightness: int = 100) -> bool:
        """Ustawia stan światła."""
        try:
            payload = {"state": state, "brightness": brightness}
            url = f"{self.simulator_url}/api/environment/devices/light/{light_id}/control"
            
            async with self.session.post(url, json=payload) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("success", False)
                else:
                    logger.error(f"Błąd sterowania {light_id}: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"Błąd wysyłania: {e}")
            return False
    
    def calculate_brightness(self, daylight: float) -> int:
        """Oblicza jasność na podstawie światła dziennego."""
        # Im więcej światła dziennego, tym mniejsza jasność
        brightness = int(100 - (daylight * 70))  # 30-100%
        return max(30, min(100, brightness))
    
    async def run_cycle(self):
        """Jeden cykl działania agenta."""
        state = await self.get_state()
        if not state:
            return
        
        power_outage = state.get("powerOutage", False)
        daylight = state.get("daylightIntensity", 1.0)
        rooms = state.get("rooms", [])
        
        if power_outage:
            logger.warning("⚡ Awaria zasilania - światła niedostępne")
            return
        
        target_brightness = self.calculate_brightness(daylight)
        
        for room in rooms:
            room_name = room.get("name", "?")
            people_count = room.get("peopleCount", 0)
            lights = room.get("lights", [])
            
            for light in lights:
                light_id = light.get("id", "")
                light_state = light.get("state", "OFF")
                light_brightness = light.get("brightness", 100)
                
                is_on = light_state == "ON"
                should_be_on = people_count > 0
                
                # Włącz światło jeśli są osoby
                if should_be_on and not is_on:
                    success = await self.set_light(light_id, "ON", target_brightness)
                    if success:
                        logger.info(f"✅ WŁĄCZONO {light_id} w {room_name} (jasność: {target_brightness}%)")
                
                # Wyłącz światło jeśli brak osób
                elif not should_be_on and is_on:
                    success = await self.set_light(light_id, "OFF")
                    if success:
                        logger.info(f"❌ WYŁĄCZONO {light_id} w {room_name}")
                
                # Dostosuj jasność jeśli potrzeba
                elif is_on and abs(light_brightness - target_brightness) > 10:
                    success = await self.set_light(light_id, "ON", target_brightness)
                    if success:
                        logger.info(f"💡 Jasność {light_id}: {light_brightness}% → {target_brightness}%")


async def main():
    """Główna funkcja."""
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    
    agent = SimpleLightAgent(url)
    
    try:
        await agent.start()
    except KeyboardInterrupt:
        agent.stop()


if __name__ == "__main__":
    asyncio.run(main())

