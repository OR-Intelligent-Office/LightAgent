# 💡 LightAgent

Inteligentny agent w Pythonie zarządzający oświetleniem budynku na podstawie danych z symulatora.

## 📋 Opis

LightAgent to autonomiczny agent, który:

- **Cyklicznie odpytuje symulator** (domyślnie co 0.5s) przez HTTP
- **Automatycznie włącza światła** gdy są osoby w pokoju (`peopleCount > 0`)
- **Automatycznie wyłącza światła** gdy nie ma osób lub jest awaria zasilania
- **Dostosowuje jasność** do poziomu światła dziennego

## 🚀 Instalacja

```bash
# Klonowanie repozytorium
cd LightAgent

# Utworzenie wirtualnego środowiska (opcjonalne)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Instalacja zależności
pip install -r requirements.txt
```

## ▶️ Uruchomienie

```bash
# Domyślne ustawienia (localhost:8080)
python main.py

# Własny serwer symulatora
python main.py --url http://192.168.1.100:8080

# Odpytywanie co 1 sekundę
python main.py --interval 1.0

# Tryb cichy (tylko akcje)
python main.py --quiet
```

## ⚙️ Opcje konfiguracji

| Parametr | Skrót | Domyślnie | Opis |
|----------|-------|-----------|------|
| `--url` | `-u` | `http://localhost:8080` | URL symulatora |
| `--interval` | `-i` | `0.5` | Interwał odpytywania (sekundy) |
| `--quiet` | `-q` | `false` | Tryb cichy |
| `--daylight-threshold` | `-d` | `0.3` | Próg światła dziennego (0.0-1.0) |
| `--no-auto-brightness` | - | `false` | Wyłącz auto-jasność |

## 🏗️ Struktura projektu

```
LightAgent/
├── main.py                 # Punkt wejścia
├── requirements.txt        # Zależności Python
├── README.md               # Dokumentacja
└── src/
    ├── __init__.py
    ├── config.py           # Konfiguracja z .env
    ├── models.py           # Modele danych (Pydantic)
    ├── simulator_client.py # Klient HTTP
    └── light_agent.py      # Agent oświetlenia
```

## 📡 API Symulatora

Agent oczekuje następujących endpointów:

### GET `/api/state`
Pobiera aktualny stan wszystkich pomieszczeń.

### POST `/api/lights/control`
Steruje światłem.

```json
{
  "lightId": "light_208_1",
  "state": "ON",
  "brightness": 80
}
```

## 🔧 Logika działania

```
┌─────────────────────────────────────────────────────────┐
│                    CYKL AGENTA                          │
├─────────────────────────────────────────────────────────┤
│  1. Pobierz stan symulatora (GET /api/state)            │
│  2. Dla każdego pokoju:                                 │
│     ├─ Sprawdź: awaria zasilania? → WYŁĄCZ              │
│     ├─ Sprawdź: peopleCount > 0? → WŁĄCZ                │
│     ├─ Sprawdź: peopleCount == 0? → WYŁĄCZ              │
│     └─ Dostosuj jasność do światła dziennego            │
│  3. Wyślij komendy sterujące                            │
│  4. Czekaj (interval) i wróć do 1.                      │
└─────────────────────────────────────────────────────────┘
```

## 📊 Przykładowy output

```
╭──────────────────── 🏢 LightAgent Status ────────────────────╮
│ Czas symulacji: 2025-12-22 10:39:48                          │
│ Światło dzienne: 70.7%                                       │
│ Temperatura zewn.: 30.7°C                                    │
│ Awaria zasilania: NIE                                        │
╰──────────────────────────────────────────────────────────────╯

              Stan pokoi
┏━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┓
┃ Pokój     ┃ Osoby  ┃ Światła  ┃ Jasność  ┃
┡━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━┩
│ Sala 208  │   0    │   0/2    │    -     │
│ Sala 209  │   0    │   0/1    │    -     │
│ Sala 210  │   2    │   3/3    │   50%    │
│ Biuro 101 │   0    │   0/1    │    -     │
└───────────┴────────┴──────────┴──────────┘

Wykonane akcje:
  ✓ WŁĄCZONO light_210_1 (Osoby w pokoju: 2, jasność: 50%)
  ✓ WŁĄCZONO light_210_2 (Osoby w pokoju: 2, jasność: 50%)
  ✓ WŁĄCZONO light_210_3 (Osoby w pokoju: 2, jasność: 50%)
```

## 📝 Wymagania

- Python 3.10+
- Symulator budynku działający na określonym URL

## 👥 Autorzy

Projekt stworzony na potrzeby zajęć z Badań Operacyjnych.

## 📄 Licencja

MIT License
