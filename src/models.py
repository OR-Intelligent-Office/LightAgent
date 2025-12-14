"""
Modele danych dla symulatora budynku.
Tylko to co potrzebne do zarządzania oświetleniem.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class LightState(str, Enum):
    """Stan światła."""
    ON = "ON"
    OFF = "OFF"


class Light(BaseModel):
    """Model światła w pokoju."""
    id: str
    room_id: str = Field(alias="roomId")
    state: LightState
    brightness: int = Field(ge=0, le=100)

    class Config:
        populate_by_name = True


class PlannedMeeting(BaseModel):
    """Zaplanowane spotkanie w pokoju (do dodania w przyszłości)."""
    id: str
    room_id: str = Field(alias="roomId")
    start_time: datetime = Field(alias="startTime")
    end_time: datetime = Field(alias="endTime")
    title: Optional[str] = None

    class Config:
        populate_by_name = True


class Room(BaseModel):
    """Model pokoju - tylko światła i liczba osób."""
    id: str
    name: str
    lights: list[Light] = []
    people_count: int = Field(default=0, alias="peopleCount")
    # TODO: planned_meetings - do dodania gdy pojawi się w JSON
    # planned_meetings: list[PlannedMeeting] = Field(default=[], alias="plannedMeetings")

    class Config:
        populate_by_name = True


class SimulatorState(BaseModel):
    """Pełny stan symulatora."""
    simulation_time: datetime = Field(alias="simulationTime")
    rooms: list[Room]
    power_outage: bool = Field(alias="powerOutage")
    daylight_intensity: float = Field(alias="daylightIntensity", ge=0.0, le=1.0)

    class Config:
        populate_by_name = True
