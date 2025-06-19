"""
pytest configuration and shared fixtures for Smart Aircon Controller tests.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any, Optional
import datetime


@pytest.fixture
def mock_hass():
    """Create a mock AppDaemon Hass instance."""
    hass = Mock()
    hass.log = Mock()
    hass.get_entity = Mock()
    hass.call_service = Mock()
    hass.set_state = Mock()
    hass.run_every = Mock()
    hass.run_in = Mock()
    hass.register_service = Mock()
    hass.get_app = Mock()
    return hass


@pytest.fixture
def mock_climate_entity():
    """Create a mock climate entity."""
    entity = Mock()
    entity.get_state = Mock(return_value="heat")
    entity.attributes = {
        "temperature": 20.0,
        "current_temperature": 19.5,
        "hvac_mode": "heat"
    }
    return entity


@pytest.fixture
def mock_damper_entity():
    """Create a mock damper entity."""
    entity = Mock()
    entity.get_state = Mock(return_value="open")
    entity.attributes = {
        "current_position": 50
    }
    return entity


@pytest.fixture
def sample_zone_configs():
    """Sample zone configurations for testing."""
    return {
        "living": {
            "climate_entity": "climate.living_2",
            "damper_entity": "cover.living_damper_2",
            "isolation": False
        },
        "baby_bed": {
            "climate_entity": "climate.baby_bed_2",
            "damper_entity": "cover.baby_bed_damper_2",
            "isolation": True
        },
        "master_bed": {
            "climate_entity": "climate.master_bed_2",
            "damper_entity": "cover.master_bed_damper_2",
            "isolation": False
        }
    }


@pytest.fixture
def sample_config():
    """Sample controller configuration for testing."""
    return {
        # Static configuration
        "check_interval": 30,
        "main_climate": "climate.aircon",
        "algorithm_timeout_minutes": 30,
        "stability_check_minutes": 10,
        "progress_timeout_minutes": 15,
        # Dynamic configuration
        "enabled": True,
        "temp_tolerance": 0.5,
        "smart_hvac_mode": "heat",
        "primary_damper_percent": 50,
        "secondary_damper_percent": 40,
        "overflow_damper_percent": 10,
        "minimum_damper_percent": 5
    }


class MockEntityBuilder:
    """Builder for creating mock entities with specific states."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self._state = "unknown"
        self._attributes = {}
        return self
    
    def with_state(self, state: str):
        self._state = state
        return self
    
    def with_temperature(self, current: float, target: float):
        self._attributes.update({
            "current_temperature": current,
            "temperature": target
        })
        return self
    
    def with_damper_position(self, position: int):
        self._attributes["current_position"] = position
        return self
    
    def build(self):
        entity = Mock()
        entity.get_state = Mock(return_value=self._state)
        entity.attributes = self._attributes.copy()
        return entity


@pytest.fixture
def entity_builder():
    """Factory for building mock entities."""
    return MockEntityBuilder()


class ZoneStateBuilder:
    """Builder for creating zone states for testing."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self._zones = {}
        return self
    
    def add_zone(self, name: str, current_temp: float, target_temp: float, 
                 is_active: bool = True, damper_position: int = 0, isolation: bool = False):
        self._zones[name] = {
            "current_temp": current_temp,
            "target_temp": target_temp,
            "is_active": is_active,
            "damper_position": damper_position,
            "isolation": isolation
        }
        return self
    
    def heating_scenario(self):
        """Common heating scenario with multiple zones."""
        return (self
                .add_zone("living", 19.0, 20.0, True, 10)
                .add_zone("baby_bed", 18.5, 20.0, True, 5, True)
                .add_zone("master_bed", 19.5, 19.0, True, 15))
    
    def cooling_scenario(self):
        """Common cooling scenario with multiple zones."""
        return (self
                .add_zone("living", 25.0, 24.0, True, 10)
                .add_zone("baby_bed", 26.0, 24.0, True, 5, True)
                .add_zone("master_bed", 23.5, 24.0, True, 15))
    
    def mixed_scenario(self):
        """Mixed active/inactive zones."""
        return (self
                .add_zone("living", 20.0, 20.0, True, 10)
                .add_zone("baby_bed", 18.5, 20.0, True, 5, True)
                .add_zone("master_bed", 22.0, 22.0, False, 0))
    
    def get_zones(self):
        return self._zones.copy()


@pytest.fixture
def zone_builder():
    """Factory for building zone states."""
    return ZoneStateBuilder()


@pytest.fixture
def mock_datetime():
    """Mock datetime for consistent testing."""
    with patch('datetime.datetime') as mock_dt:
        mock_dt.now.return_value = datetime.datetime(2023, 1, 1, 12, 0, 0)
        yield mock_dt


@pytest.fixture
def temp_history_builder():
    """Builder for temperature history data."""
    def _build_history(zone_name: str, temps: list, interval_minutes: int = 1) -> list:
        """Build temperature history with timestamps."""
        history = []
        base_time = datetime.datetime.now()
        for i, temp in enumerate(temps):
            timestamp = base_time - datetime.timedelta(minutes=len(temps) - i - 1)
            history.append((timestamp, temp))
        return history
    return _build_history


class ServiceCallTracker:
    """Helper to track service calls made during tests."""
    
    def __init__(self):
        self.calls = []
    
    def track_call(self, service: str, **kwargs):
        self.calls.append({
            "service": service,
            "kwargs": kwargs
        })
    
    def get_calls(self, service: str = None):
        if service:
            return [call for call in self.calls if call["service"] == service]
        return self.calls.copy()
    
    def clear(self):
        self.calls.clear()
    
    def has_call(self, service: str, **expected_kwargs) -> bool:
        for call in self.calls:
            if call["service"] == service:
                if all(call["kwargs"].get(k) == v for k, v in expected_kwargs.items()):
                    return True
        return False


@pytest.fixture
def service_tracker():
    """Service call tracker for testing."""
    return ServiceCallTracker()