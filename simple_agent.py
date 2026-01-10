#!/usr/bin/env python3
"""
Prosty LightAgent - pobiera stan z symulatora i steruje światłami.

Funkcje:
- Włącza światła gdy są osoby w pokoju
- Włącza światła 1 minutę przed zaplanowanym spotkaniem
- Wyłącza światła po 5 minutach bez osób
- Dostosowuje jasność do światła dziennego
- Wykrywa awarie świateł (BROKEN)
"""

import asyncio
import aiohttp
import logging
import sys
from datetime import datetime

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
        self.min_illumination_lux = 700  # Minimalne naświetlenie dla komfortu (lux)
        self.minutes_before_meeting = 1 
        self.minutes_to_turn_off = 5
        self.max_light_lux = 500  # Maksymalne światło z jednego światła (brightness 100%) 
        
        # room_id -> simulation_time kiedy ostatnio były osoby
        self.last_people_time: dict[str, datetime] = {}
        
        # Śledzenie zepsutych świateł (żeby nie logować ciągle)
        self.broken_lights: set[str] = set()
    
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
    
    def calculate_light_contribution(self, light: dict) -> float:
        """
        Oblicza ile lux daje dane światło (jeśli jest włączone).
        """
        if light.get("state") != "ON":
            return 0.0
        brightness = light.get("brightness", 100)
        return (brightness / 100.0) * self.max_light_lux
    
    def calculate_illumination_after_turning_off(self, current_illumination: float, lights_to_turn_off: list) -> float:
        """
        Oblicza jakie będzie illumination po wyłączeniu danych świateł.
        """
        light_contribution = sum(self.calculate_light_contribution(light) for light in lights_to_turn_off)
        return current_illumination - light_contribution
    
    def calculate_optimal_brightness_for_lights(self, current_illumination: float, lights_on: list) -> list[tuple[str, int]]:
        """
        Oblicza optymalny brightness dla włączonych świateł, żeby osiągnąć min_illumination_lux.
        Zwraca listę tuple (light_id, target_brightness).
        """
        if not lights_on:
            return []
        
        if current_illumination >= self.min_illumination_lux:
            # Wystarczające oświetlenie - można zmniejszyć brightness, ale to będzie obsłużone w innej logice
            return []
        
        # Oblicz ile lux dają obecnie włączone światła
        current_lights_lux = sum(self.calculate_light_contribution(light) for light in lights_on)
        # Oblicz światło zewnętrzne (illumination - światło z lamp)
        external_light = current_illumination - current_lights_lux
        
        # Oblicz ile brakuje luxów
        needed_lux = self.min_illumination_lux - current_illumination
        
        # Oblicz ile luxów trzeba dodać do włączonych świateł
        target_lights_lux = current_lights_lux + needed_lux
        
        # Rozłóż target_lights_lux równomiernie na wszystkie włączone światła
        target_lux_per_light = target_lights_lux / len(lights_on)
        target_brightness_per_light = int((target_lux_per_light / self.max_light_lux) * 100)
        target_brightness_per_light = max(1, min(100, target_brightness_per_light))  # Ograniczenie 1-100
        
        result = []
        for light in lights_on:
            light_id = light.get("id", "")
            current_brightness = light.get("brightness", 100)
            # Aktualizuj tylko jeśli brightness się zmieni (różnica > 5%)
            if abs(current_brightness - target_brightness_per_light) > 5:
                result.append((light_id, target_brightness_per_light))
        
        return result
    
    def calculate_lights_needed(self, current_illumination: float, working_lights: list) -> tuple[int, int]:
        """
        Oblicza ile świateł potrzeba włączyć i jaki brightness ustawić, żeby osiągnąć min_illumination_lux.
        Zwraca tuple (liczba świateł do włączenia, brightness dla ostatniego światła 0-100).
        Jeśli wystarczające oświetlenie, zwraca (0, 0).
        """
        if current_illumination >= self.min_illumination_lux:
            return (0, 0)
        
        needed_lux = self.min_illumination_lux - current_illumination
        
        # Oblicz ile pełnych świateł potrzeba (100% brightness)
        full_lights_needed = int(needed_lux / self.max_light_lux)
        remaining_lux = needed_lux - (full_lights_needed * self.max_light_lux)
        
        # Jeśli potrzeba tylko częściowe światło dla ostatniego
        if remaining_lux > 0:
            # Oblicz brightness dla ostatniego światła (remaining_lux / max_light_lux * 100)
            last_light_brightness = int((remaining_lux / self.max_light_lux) * 100)
            lights_needed = full_lights_needed + 1
        else:
            last_light_brightness = 100  # Ostatnie światło też na 100%
            lights_needed = full_lights_needed
        
        lights_needed = min(lights_needed, len(working_lights))
        return (lights_needed, last_light_brightness)
    
    def has_upcoming_meeting(self, meetings: list, simulation_time: datetime) -> bool:
        for meeting in meetings:
            try:
                start_time = datetime.fromisoformat(meeting.get("startTime", ""))
                time_until = (start_time - simulation_time).total_seconds() / 60
                
                if 0 <= time_until <= self.minutes_before_meeting:
                    return True
                    
                end_time = datetime.fromisoformat(meeting.get("endTime", ""))
                if start_time <= simulation_time <= end_time:
                    return True
                    
            except (ValueError, TypeError):
                continue
        return False
    
    def should_turn_off(self, room_id: str, simulation_time: datetime) -> bool:
        """Sprawdza czy minęło wystarczająco dużo czasu (symulacji) bez osób."""
        last_time = self.last_people_time.get(room_id)
        if last_time is None:
            return True  # Nigdy nie było osób - gasić
        
        minutes_without_people = (simulation_time - last_time).total_seconds() / 60
        return minutes_without_people >= self.minutes_to_turn_off
    
    async def run_cycle(self):
        state = await self.get_state()
        if not state:
            return
        
        power_outage = state.get("powerOutage", False)
        rooms = state.get("rooms", [])
        
        try:
            sim_time_str = state.get("simulationTime", "")
            simulation_time = datetime.fromisoformat(sim_time_str)
        except (ValueError, TypeError):
            simulation_time = datetime.now()
        
        if power_outage:
            logger.warning("Awaria zasilania - światła niedostępne")
            return
        
        for room in rooms:
            room_id = room.get("id", "")
            room_name = room.get("name", "?")
            people_count = room.get("peopleCount", 0)
            lights = room.get("lights", [])
            meetings = room.get("scheduledMeetings", [])
            illumination = room.get("illumination", 0.0)
            
            # Używamy czasu symulacji do śledzenia obecności osób
            if people_count > 0:
                self.last_people_time[room_id] = simulation_time
            
            meeting_soon = self.has_upcoming_meeting(meetings, simulation_time)
            needs_lighting = people_count > 0 or meeting_soon
            
            # Filtruj tylko działające światła (nie BROKEN)
            working_lights = [l for l in lights if l.get("state") != "BROKEN"]
            
            # Sprawdź czy światła są zepsute/naprawione
            for light in lights:
                light_id = light.get("id", "")
                light_state = light.get("state", "OFF")
                is_broken = light_state == "BROKEN"
                
                if is_broken:
                    if light_id not in self.broken_lights:
                        self.broken_lights.add(light_id)
                        logger.warning(f"AWARIA {light_id} w {room_name} - światło zepsute!")
                else:
                    if light_id in self.broken_lights:
                        self.broken_lights.remove(light_id)
                        logger.info(f"NAPRAWIONO {light_id} w {room_name}")
            
            if not needs_lighting:
                # Wyłącz wszystkie światła jeśli minęło wystarczająco czasu
                if self.should_turn_off(room_id, simulation_time):
                    for light in working_lights:
                        light_id = light.get("id", "")
                        light_state = light.get("state", "OFF")
                        if light_state == "ON":
                            success = await self.set_light(light_id, "OFF")
                            if success:
                                logger.info(f"WYŁĄCZONO {light_id} w {room_name} (brak osób przez {self.minutes_to_turn_off} min symulacji)")
                continue
            
            # Sprawdź czy pokój jest dostatecznie doświetlony
            if illumination >= self.min_illumination_lux:
                # Wystarczające oświetlenie - sprawdź czy można bezpiecznie wyłączyć światła
                lights_on = [l for l in working_lights if l.get("state") == "ON"]
                if lights_on:
                    # Sprawdź illumination po wyłączeniu wszystkich świateł
                    illumination_after = self.calculate_illumination_after_turning_off(illumination, lights_on)
                    if illumination_after >= self.min_illumination_lux:
                        # Bezpiecznie wyłącz wszystkie światła (oszczędność energii)
                        for light in lights_on:
                            light_id = light.get("id", "")
                            success = await self.set_light(light_id, "OFF")
                            if success:
                                logger.info(f"WYŁĄCZONO {light_id} w {room_name} (wystarczające oświetlenie: {illumination:.0f} lux, po wyłączeniu: {illumination_after:.0f} lux)")
                    # Jeśli illumination_after < min_illumination_lux, NIE wyłączaj - światła są potrzebne
                continue
            
            # Potrzebne jest dodatkowe oświetlenie
            # Oblicz ile świateł jest obecnie włączonych
            lights_on = [l for l in working_lights if l.get("state") == "ON"]
            lights_off = [l for l in working_lights if l.get("state") == "OFF"]
            
            # Najpierw zaktualizuj brightness włączonych świateł jeśli potrzeba
            if lights_on:
                brightness_updates = self.calculate_optimal_brightness_for_lights(illumination, lights_on)
                for light_id, target_brightness in brightness_updates:
                    success = await self.set_light(light_id, "ON", target_brightness)
                    if success:
                        logger.info(f"AKTUALIZOWANO brightness {light_id} w {room_name} do {target_brightness}% (oświetlenie: {illumination:.0f} lux)")
            
            # Oblicz ile świateł potrzeba włączyć i jaki brightness (uwzględniając aktualne illumination)
            lights_needed, last_light_brightness = self.calculate_lights_needed(illumination, lights_off)
            
            if lights_needed == 0:
                # Wystarczające oświetlenie - wyłącz nadmiarowe światła (ale sprawdź czy bezpiecznie)
                if len(lights_on) > 1:
                    # Wyłącz wszystkie oprócz pierwszego (jeśli jest tylko jedno, nic nie rób)
                    lights_to_turn_off = lights_on[1:]
                    illumination_after = self.calculate_illumination_after_turning_off(illumination, lights_to_turn_off)
                    if illumination_after >= self.min_illumination_lux:
                        # Bezpiecznie wyłącz nadmiarowe światła
                        for light in lights_to_turn_off:
                            light_id = light.get("id", "")
                            success = await self.set_light(light_id, "OFF")
                            if success:
                                logger.info(f"WYŁĄCZONO {light_id} w {room_name} (oszczędność energii, oświetlenie: {illumination:.0f} -> {illumination_after:.0f} lux)")
                    # Jeśli illumination_after < min_illumination_lux, NIE wyłączaj - wszystkie światła są potrzebne
            else:
                # Włącz tylko tyle świateł ile potrzeba z odpowiednim brightness
                lights_to_turn_on = lights_off[:lights_needed]
                reason = "spotkanie za chwilę" if meeting_soon else f"{people_count} os."
                
                for i, light in enumerate(lights_to_turn_on):
                    light_id = light.get("id", "")
                    # Ostatnie światło ma custom brightness, pozostałe na 100%
                    brightness = last_light_brightness if i == len(lights_to_turn_on) - 1 else 100
                    expected_lux_added = (brightness / 100.0) * self.max_light_lux
                    success = await self.set_light(light_id, "ON", brightness)
                    if success:
                        logger.info(f"WŁĄCZONO {light_id} w {room_name} ({reason}, brightness: {brightness}%, oświetlenie: {illumination:.0f} -> {illumination + expected_lux_added:.0f} lux)")
                
                # Jeśli pokój ma więcej niż jedno światło i wszystkie są włączone, 
                # ale nadal za mało oświetlenia - to oznacza że pokój ma tylko jedno światło
                # W takim przypadku nic więcej nie można zrobić


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    
    agent = SimpleLightAgent(url)
    
    try:
        await agent.start()
    except KeyboardInterrupt:
        agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
