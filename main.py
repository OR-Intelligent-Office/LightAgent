#!/usr/bin/env python3
"""
LightAgent - Inteligentny agent zarządzający oświetleniem budynku.

Uruchomienie:
    python main.py [--url URL] [--interval SECONDS] [--quiet]

Przykłady:
    python main.py
    python main.py --url http://192.168.1.100:8080
    python main.py --interval 1.0 --quiet
"""

import asyncio
import argparse
import signal
import sys
from rich.console import Console
from rich.panel import Panel

from src.simulator_client import SimulatorClient
from src.light_agent import LightAgent, LightAgentConfig

console = Console()


def parse_args() -> argparse.Namespace:
    """Parsuje argumenty wiersza poleceń."""
    parser = argparse.ArgumentParser(
        description="LightAgent - Inteligentny agent zarządzający oświetleniem",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady użycia:
  python main.py                          # Domyślne ustawienia
  python main.py --url http://server:8080 # Własny serwer
  python main.py --interval 1.0           # Odpytywanie co 1 sekundę
  python main.py --quiet                  # Tryb cichy
  python main.py --no-auto-brightness     # Stała jasność
        """
    )
    
    parser.add_argument(
        "--url", "-u",
        type=str,
        default="http://localhost:8080",
        help="URL symulatora (domyślnie: http://localhost:8080)"
    )
    
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=0.5,
        help="Interwał odpytywania w sekundach (domyślnie: 0.5)"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Tryb cichy - tylko akcje"
    )
    
    parser.add_argument(
        "--daylight-threshold", "-d",
        type=float,
        default=0.3,
        help="Próg światła dziennego (0.0-1.0, domyślnie: 0.3)"
    )
    
    parser.add_argument(
        "--no-auto-brightness",
        action="store_true",
        help="Wyłącz automatyczne dostosowanie jasności"
    )
    
    return parser.parse_args()


async def main():
    """Główna funkcja programu."""
    args = parse_args()
    
    # Konfiguracja agenta
    config = LightAgentConfig(
        poll_interval=args.interval,
        daylight_threshold=args.daylight_threshold,
        auto_brightness=not args.no_auto_brightness,
    )
    
    console.print(Panel(
        f"[bold]URL symulatora:[/bold] {args.url}\n"
        f"[bold]Interwał:[/bold] {config.poll_interval}s\n"
        f"[bold]Próg światła:[/bold] {config.daylight_threshold:.0%}\n"
        f"[bold]Auto-jasność:[/bold] {'Tak' if config.auto_brightness else 'Nie'}",
        title="⚙️ Konfiguracja LightAgent",
        border_style="blue"
    ))
    console.print()
    
    # Uruchomienie agenta
    async with SimulatorClient(args.url) as client:
        agent = LightAgent(client, config)
        
        # Obsługa sygnałów (Ctrl+C)
        loop = asyncio.get_event_loop()
        
        def signal_handler():
            console.print("\n[yellow]Otrzymano sygnał zatrzymania...[/yellow]")
            agent.stop()
        
        # Windows nie wspiera add_signal_handler w asyncio
        if sys.platform != "win32":
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, signal_handler)
        
        try:
            await agent.run(verbose=not args.quiet)
        except KeyboardInterrupt:
            agent.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold red]Przerwano przez użytkownika[/bold red]")
        sys.exit(0)
