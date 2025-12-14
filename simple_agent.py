#!/usr/bin/env python3
"""
Prosty LightAgent - pobiera stan z symulatora i steruje światłami.

Funkcje:
- Włącza światła gdy są osoby w pokoju
- Włącza światła 1 minutę przed zaplanowanym spotkaniem
- Wyłącza światła po 5 minutach bez osób
- Dostosowuje jasność do światła dziennego
"""

import asyncio
import aiohttp
import logging
import sys
from datetime import datetime, timedelta

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
        self.poll_interval = 2.0  
        self.daylight_threshold = 0.3 
        self.minutes_before_meeting = 1 
        self.minutes_to_turn_off = 5 
        
        # room_id -> datetime kiedy ostatnio były osoby
        self.last_people_time: dict[str, datetime] = {}
    
    async def start(self):
        self.session = aiohttp.ClientSession()
        self.running = True
        logger.info(f"LightAgent uruchomiony - {self.simulator_url}")
        logger.info(f"Włączanie przed spotkaniem: {self.minutes_before_meeting} min")
        logger.info(f"Wyłączanie po braku osób: {self.minutes_to_turn_off} min")
        
        try:
            while self.running:
                await self.run_cycle()
                await asyncio.sleep(self.poll_interval)
        finally:
            await self.session.close()
    
    def stop(self):
        self.running = False
        logger.info("LightAgent zatrzymany")
    
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
        brightness = int(100 - (daylight * 70))  # 30-100%
        return max(30, min(100, brightness))
    
    def has_upcoming_meeting(self, meetings: list, simulation_time: datetime) -> bool:
        """Sprawdza czy jest spotkanie w ciągu X minut."""
        for meeting in meetings:
            try:
                start_time = datetime.fromisoformat(meeting.get("startTime", ""))
                time_until = (start_time - simulation_time).total_seconds() / 60  # minuty
                
                # Spotkanie zaczyna się za 0-X minut
                if 0 <= time_until <= self.minutes_before_meeting:
                    return True
                    
                # Spotkanie trwa
                end_time = datetime.fromisoformat(meeting.get("endTime", ""))
                if start_time <= simulation_time <= end_time:
                    return True
                    
            except (ValueError, TypeError):
                continue
        return False
    
    def should_turn_off(self, room_id: str, current_time: datetime) -> bool:
        """Sprawdza czy minęło wystarczająco czasu bez osób aby wyłączyć."""
        last_time = self.last_people_time.get(room_id)
        if last_time is None:
            return True  
        
        minutes_without_people = (current_time - last_time).total_seconds() / 60
        return minutes_without_people >= self.minutes_to_turn_off
    
    async def run_cycle(self):
        """Jeden cykl działania agenta."""
        state = await self.get_state()
        if not state:
            return
        
        power_outage = state.get("powerOutage", False)
        daylight = state.get("daylightIntensity", 1.0)
        rooms = state.get("rooms", [])
        
        try:
            sim_time_str = state.get("simulationTime", "")
            simulation_time = datetime.fromisoformat(sim_time_str)
        except (ValueError, TypeError):
            simulation_time = datetime.now()
        
        if power_outage:
            logger.warning("⚡ Awaria zasilania - światła niedostępne")
            return
        
        target_brightness = self.calculate_brightness(daylight)
        current_time = datetime.now()
        
        for room in rooms:
            room_id = room.get("id", "")
            room_name = room.get("name", "?")
            people_count = room.get("peopleCount", 0)
            lights = room.get("lights", [])
            meetings = room.get("scheduledMeetings", [])
            
            if people_count > 0:
                self.last_people_time[room_id] = current_time
            e
            meeting_soon = self.has_upcoming_meeting(meetings, simulation_time)
            
            should_be_on = people_count > 0 or meeting_soon
            
            for light in lights:
                light_id = light.get("id", "")
                light_state = light.get("state", "OFF")
                light_brightness = light.get("brightness", 100)
                
                is_on = light_state == "ON"
                

                if should_be_on and not is_on:
                    reason = "spotkanie za chwilę" if meeting_soon else f"{people_count} os."
                    success = await self.set_light(light_id, "ON", target_brightness)
                    if success:
                        logger.info(f"WŁĄCZONO {light_id} w {room_name} ({reason}, jasność: {target_brightness}%)")
                
                elif not should_be_on and is_on:
                    if self.should_turn_off(room_id, current_time):
                        success = await self.set_light(light_id, "OFF")
                        if success:
                            logger.info(f"WYŁĄCZONO {light_id} w {room_name} (brak osób przez {self.minutes_to_turn_off} min)")
                
                elif is_on and abs(light_brightness - target_brightness) > 10:
                    success = await self.set_light(light_id, "ON", target_brightness)
                    if success:
                        logger.info(f"Jasność {light_id}: {light_brightness}% → {target_brightness}%")


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    
    agent = SimpleLightAgent(url)
    
    try:
        await agent.start()
    except KeyboardInterrupt:
        agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
