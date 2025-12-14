"""
LightAgent - Inteligentny agent zarządzający oświetleniem.

Agent podejmuje decyzje na podstawie:
- Liczby osób w pomieszczeniu (peopleCount)
- Poziomu światła dziennego
- Stanu awarii zasilania
"""

import asyncio
from dataclasses import dataclass
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .models import SimulatorState, Room, LightState
from .simulator_client import SimulatorClient

console = Console()


@dataclass
class LightAgentConfig:
    """Konfiguracja agenta oświetlenia."""
    
    # Próg światła dziennego - poniżej tej wartości włączamy światła
    daylight_threshold: float = 0.3
    
    # Minimalna jasność przy wysokim poziomie światła dziennego
    min_brightness: int = 30
    
    # Maksymalna jasność przy niskim poziomie światła dziennego
    max_brightness: int = 100
    
    # Czy automatycznie dostosowywać jasność do światła dziennego
    auto_brightness: bool = True
    
    # Interwał odpytywania symulatora (sekundy)
    poll_interval: float = 0.5


@dataclass
class RoomState:
    """Stan pokoju śledzony przez agenta."""
    room_id: str
    lights_on: bool = False
    current_brightness: int = 100


class LightAgent:
    """
    Inteligentny agent zarządzający oświetleniem budynku.
    
    Logika działania:
    1. Włącz światła gdy:
       - Są osoby w pokoju (peopleCount > 0)
       - NIE ma awarii zasilania
       
    2. Wyłącz światła gdy:
       - NIE ma osób w pokoju (peopleCount == 0)
       - LUB jest awaria zasilania
       
    3. Dostosuj jasność do poziomu światła dziennego
    """

    def __init__(
        self, 
        client: SimulatorClient, 
        config: Optional[LightAgentConfig] = None
    ):
        """
        Inicjalizacja agenta.
        
        Args:
            client: Klient symulatora
            config: Konfiguracja agenta
        """
        self.client = client
        self.config = config or LightAgentConfig()
        self.room_states: dict[str, RoomState] = {}
        self.running = False
        self._last_state: Optional[SimulatorState] = None

    def _get_room_state(self, room_id: str) -> RoomState:
        """Pobiera lub tworzy stan pokoju."""
        if room_id not in self.room_states:
            self.room_states[room_id] = RoomState(room_id=room_id)
        return self.room_states[room_id]

    def _calculate_brightness(self, daylight_intensity: float) -> int:
        """
        Oblicza odpowiednią jasność na podstawie światła dziennego.
        
        Im więcej światła dziennego, tym mniejsza jasność sztucznego oświetlenia.
        """
        if not self.config.auto_brightness:
            return self.config.max_brightness
            
        # Odwrotna proporcja - więcej światła dziennego = mniej sztucznego
        brightness_range = self.config.max_brightness - self.config.min_brightness
        brightness = int(
            self.config.max_brightness - (daylight_intensity * brightness_range)
        )
        return max(self.config.min_brightness, min(self.config.max_brightness, brightness))

    def _should_lights_be_on(
        self, 
        room: Room, 
        state: SimulatorState
    ) -> tuple[bool, str]:
        """
        Decyduje czy światła powinny być włączone.
        
        Returns:
            Tuple (czy_włączyć, powód)
        """
        # Awaria zasilania - zawsze wyłączamy
        if state.power_outage:
            return False, "Awaria zasilania"
        
        # Sprawdzamy czy są osoby w pokoju
        if room.people_count > 0:
            return True, f"Osoby w pokoju: {room.people_count}"
        
        # Brak osób - wyłączamy
        return False, "Brak osób"

    def _needs_light_due_to_darkness(self, daylight_intensity: float) -> bool:
        """Sprawdza czy potrzebne jest sztuczne oświetlenie ze względu na ciemność."""
        return daylight_intensity < self.config.daylight_threshold

    async def _process_room(self, room: Room, state: SimulatorState) -> list[str]:
        """
        Przetwarza pojedynczy pokój i podejmuje decyzje o oświetleniu.
        
        Returns:
            Lista wykonanych akcji
        """
        actions = []
        room_state = self._get_room_state(room.id)
        
        should_be_on, reason = self._should_lights_be_on(room, state)
        target_brightness = self._calculate_brightness(state.daylight_intensity)
        
        for light in room.lights:
            current_on = light.state == LightState.ON
            
            if should_be_on and not current_on:
                # Włączamy światło
                success = await self.client.turn_on_light(light.id, target_brightness)
                if success:
                    actions.append(
                        f"[green]✓ WŁĄCZONO[/green] {light.id} ({reason}, jasność: {target_brightness}%)"
                    )
                    room_state.lights_on = True
                    room_state.current_brightness = target_brightness
                    
            elif not should_be_on and current_on:
                # Wyłączamy światło
                success = await self.client.turn_off_light(light.id)
                if success:
                    actions.append(
                        f"[red]✗ WYŁĄCZONO[/red] {light.id} ({reason})"
                    )
                    room_state.lights_on = False
                    
            elif should_be_on and current_on:
                # Sprawdzamy czy trzeba dostosować jasność
                if self.config.auto_brightness and light.brightness != target_brightness:
                    success = await self.client.turn_on_light(light.id, target_brightness)
                    if success:
                        actions.append(
                            f"[yellow]↔ JASNOŚĆ[/yellow] {light.id}: {light.brightness}% → {target_brightness}%"
                        )
                        room_state.current_brightness = target_brightness
        
        return actions

    async def process_state(self, state: SimulatorState) -> list[str]:
        """
        Przetwarza stan symulatora i podejmuje decyzje dla wszystkich pokoi.
        
        Returns:
            Lista wszystkich wykonanych akcji
        """
        all_actions = []
        
        for room in state.rooms:
            actions = await self._process_room(room, state)
            all_actions.extend(actions)
        
        self._last_state = state
        return all_actions

    def _print_status(self, state: SimulatorState, actions: list[str]):
        """Wyświetla status agenta."""
        # Status header
        console.print(Panel(
            f"[bold cyan]Czas symulacji:[/bold cyan] {state.simulation_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"[bold cyan]Światło dzienne:[/bold cyan] {state.daylight_intensity:.1%}\n"
            f"[bold cyan]Temperatura zewn.:[/bold cyan] {state.external_temperature:.1f}°C\n"
            f"[bold cyan]Awaria zasilania:[/bold cyan] {'[red]TAK[/red]' if state.power_outage else '[green]NIE[/green]'}",
            title="🏢 LightAgent Status",
            border_style="cyan"
        ))
        
        # Rooms table
        table = Table(title="Stan pokoi", show_header=True, header_style="bold magenta")
        table.add_column("Pokój", style="cyan")
        table.add_column("Osoby", justify="center")
        table.add_column("Światła", justify="center")
        table.add_column("Jasność", justify="center")
        
        for room in state.rooms:
            lights_on = sum(1 for l in room.lights if l.state == LightState.ON)
            lights_total = len(room.lights)
            lights_str = f"{lights_on}/{lights_total}" if lights_total > 0 else "-"
            
            avg_brightness = "-"
            if lights_on > 0:
                avg = sum(l.brightness for l in room.lights if l.state == LightState.ON) / lights_on
                avg_brightness = f"{avg:.0f}%"
            
            table.add_row(
                room.name,
                str(room.people_count),
                lights_str,
                avg_brightness
            )
        
        console.print(table)
        
        # Actions
        if actions:
            console.print("\n[bold yellow]Wykonane akcje:[/bold yellow]")
            for action in actions:
                console.print(f"  {action}")
        console.print()

    async def run(self, verbose: bool = True):
        """
        Uruchamia główną pętlę agenta.
        
        Args:
            verbose: Czy wyświetlać szczegółowe informacje
        """
        self.running = True
        console.print("[bold green]🚀 LightAgent uruchomiony[/bold green]")
        console.print(f"[dim]Odpytywanie co {self.config.poll_interval}s...[/dim]\n")
        
        while self.running:
            try:
                state = await self.client.get_state()
                
                if state is None:
                    console.print("[yellow]⚠ Nie udało się pobrać stanu symulatora[/yellow]")
                    await asyncio.sleep(self.config.poll_interval)
                    continue
                
                actions = await self.process_state(state)
                
                if verbose:
                    console.clear()
                    self._print_status(state, actions)
                elif actions:
                    for action in actions:
                        console.print(action)
                
                await asyncio.sleep(self.config.poll_interval)
                
            except asyncio.CancelledError:
                console.print("\n[yellow]Agent zatrzymany[/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Błąd: {e}[/red]")
                await asyncio.sleep(self.config.poll_interval)
        
        console.print("[bold red]🛑 LightAgent zatrzymany[/bold red]")

    def stop(self):
        """Zatrzymuje agenta."""
        self.running = False
