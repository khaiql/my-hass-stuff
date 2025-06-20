"""
Tests for StateManager class.
Following TDD approach - write tests first, then implement.
"""
import pytest
from unittest.mock import Mock, patch
import datetime
from typing import Dict

# Direct import from the module file
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smart_aircon_controller.smart_aircon_controller import StateManager, ZoneState, HVACMode, ControllerConfig


class TestStateManagerInitialization:
    """Test StateManager initialization."""

    def test_initialization_success(self, mock_hass, sample_config, sample_zone_configs):
        """StateManager should initialize with valid configuration."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        assert state_manager.hass == mock_hass
        assert state_manager.config == config
        assert len(state_manager.zones) == 3
        assert state_manager.current_hvac_mode is None
        assert state_manager.controller_ref is None

    def test_initialization_with_missing_config(self, mock_hass, sample_config):
        """StateManager should handle missing zone configuration gracefully."""
        config = ControllerConfig(**sample_config)
        zones_config = {
            "invalid_zone": {
                "climate_entity": "climate.living"
                # Missing damper_entity
            }
        }
        
        state_manager = StateManager(mock_hass, config, zones_config)
        assert len(state_manager.zones) == 0  # Zone should not be created

    def test_initialization_with_exception(self, mock_hass, sample_config):
        """StateManager should handle exceptions during zone initialization."""
        config = ControllerConfig(**sample_config)
        zones_config = {
            "problem_zone": {
                "climate_entity": None,  # This will cause an exception
                "damper_entity": "cover.living_damper"
            }
        }
        
        # Should not raise exception
        state_manager = StateManager(mock_hass, config, zones_config)


class TestStateManagerZoneUpdates:
    """Test zone state update functionality."""

    def test_update_all_zones_success(self, mock_hass, sample_config, sample_zone_configs):
        """Should update all zone states from Home Assistant."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock entity responses
        def mock_get_entity(entity_id):
            entity = Mock()
            if "climate" in entity_id:
                entity.get_state.return_value = "heat"
                entity.attributes = {
                    "temperature": 20.0,
                    "current_temperature": 19.5
                }
            else:  # damper
                entity.attributes = {"current_position": 50}
            return entity
        
        mock_hass.get_entity = mock_get_entity
        
        state_manager.update_all_zones()
        
        # Check zone states were updated
        living_zone = state_manager.zones["living"]
        assert living_zone.is_active is True
        assert living_zone.current_temp == 19.5
        assert living_zone.target_temp == 20.0
        assert living_zone.damper_position == 50

    def test_update_single_zone_with_unavailable_entity(self, mock_hass, sample_config, sample_zone_configs):
        """Should handle unavailable entities gracefully."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock unavailable climate entity
        def mock_get_entity(entity_id):
            entity = Mock()
            if "climate" in entity_id:
                entity.get_state.return_value = "unavailable"
                entity.attributes = {}
            else:  # damper
                entity.attributes = {"current_position": 50}
            return entity
        
        mock_hass.get_entity = mock_get_entity
        
        state_manager.update_all_zones()
        
        # Zone should not be active when climate entity unavailable
        living_zone = state_manager.zones["living"]
        assert living_zone.is_active is False

    def test_update_zone_with_exception(self, mock_hass, sample_config, sample_zone_configs):
        """Should handle exceptions during zone updates."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock exception
        mock_hass.get_entity.side_effect = Exception("Entity not found")
        
        # Should not raise exception
        state_manager.update_all_zones()

    def test_update_temperature_history(self, mock_hass, sample_config, sample_zone_configs):
        """Should maintain temperature history with proper cleanup."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Add temperature readings over time
        now = datetime.datetime.now()
        old_time = now - datetime.timedelta(minutes=35)  # Should be cleaned up
        recent_time = now - datetime.timedelta(minutes=5)  # Should be kept
        
        state_manager.temperature_history["living"] = [
            (old_time, 18.0),
            (recent_time, 19.0)
        ]
        
        # Update with new temperature
        state_manager._update_temperature_history("living", 19.5)
        
        # Old entry should be cleaned up, recent ones kept
        history = state_manager.temperature_history["living"]
        assert len(history) == 2  # recent + new
        assert all(time > now - datetime.timedelta(minutes=30) for time, _ in history)

    def test_update_hvac_mode_success(self, mock_hass, sample_config, sample_zone_configs):
        """Should update HVAC mode from main climate entity."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock main climate entity
        main_entity = Mock()
        main_entity.get_state.return_value = "heat"
        mock_hass.get_entity.return_value = main_entity
        
        state_manager.update_hvac_mode()
        
        assert state_manager.current_hvac_mode == "heat"

    def test_update_hvac_mode_exception(self, mock_hass, sample_config, sample_zone_configs):
        """Should handle exceptions when updating HVAC mode."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock exception
        mock_hass.get_entity.side_effect = Exception("Entity error")
        
        state_manager.update_hvac_mode()
        
        assert state_manager.current_hvac_mode == "unknown"


class TestStateManagerZoneQueries:
    """Test zone query functionality."""

    def test_get_active_zones(self, mock_hass, sample_config, sample_zone_configs):
        """Should return list of active zone names."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Set some zones active
        state_manager.zones["living"].is_active = True
        state_manager.zones["master_bed"].is_active = True
        state_manager.zones["baby_bed"].is_active = False
        
        active_zones = state_manager.get_active_zones()
        
        assert "living" in active_zones
        assert "master_bed" in active_zones
        assert "baby_bed" not in active_zones

    def test_get_active_zones_returns_empty_when_no_active_zones(self, mock_hass, sample_config, sample_zone_configs):
        """Should return empty list when no zones are active."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Set all zones inactive
        for zone in state_manager.zones.values():
            zone.is_active = False
        
        active_zones = state_manager.get_active_zones()
        
        assert active_zones == []
        assert len(active_zones) == 0

    def test_get_zones_needing_heating_wrong_mode(self, mock_hass, sample_config, sample_zone_configs):
        """Should return empty list when not in heating mode."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "cool"  # Not heat mode
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        zones = state_manager.get_zones_needing_heating()
        assert zones == []

    def test_get_zones_needing_cooling_wrong_mode(self, mock_hass, sample_config, sample_zone_configs):
        """Should return empty list when not in cooling mode."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "heat"  # Not cool mode
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        zones = state_manager.get_zones_needing_cooling()
        assert zones == []

    def test_all_dampers_low_no_active_zones(self, mock_hass, sample_config, sample_zone_configs):
        """Should return True when no active zones."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # All zones inactive
        for zone in state_manager.zones.values():
            zone.is_active = False
        
        assert state_manager.all_dampers_low() is True

    def test_all_dampers_low_mixed_positions(self, mock_hass, sample_config, sample_zone_configs):
        """Should check damper positions correctly."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Set zones active with different damper positions
        state_manager.zones["living"].is_active = True
        state_manager.zones["living"].damper_position = 5  # Low
        state_manager.zones["master_bed"].is_active = True
        state_manager.zones["master_bed"].damper_position = 15  # High
        
        assert state_manager.all_dampers_low(threshold=10) is False
        assert state_manager.all_dampers_low(threshold=20) is True

    def test_is_temperature_stable_not_enough_history(self, mock_hass, sample_config, sample_zone_configs):
        """Should return False when not enough temperature history."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # No temperature history
        result = state_manager.is_temperature_stable("living")
        assert result is False

    def test_is_temperature_stable_recent_history(self, mock_hass, sample_config, sample_zone_configs):
        """Should check temperature stability correctly."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        now = datetime.datetime.now()
        
        # Add stable temperature history with enough data points within the 5-minute window
        state_manager.temperature_history["living"] = [
            (now - datetime.timedelta(minutes=10), 19.5),  # Outside window
            (now - datetime.timedelta(minutes=4), 20.0),   # Within window
            (now - datetime.timedelta(minutes=3), 20.1),   # Within window
            (now - datetime.timedelta(minutes=2), 20.0),   # Within window
            (now - datetime.timedelta(minutes=1), 20.05),  # Within window
            (now, 20.0)                                    # Within window
        ]
        
        result = state_manager.is_temperature_stable("living", minutes=5, threshold=0.2)
        assert result is True

    def test_is_temperature_stable_unstable_temps(self, mock_hass, sample_config, sample_zone_configs):
        """Should detect unstable temperatures."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        now = datetime.datetime.now()
        
        # Add unstable temperature history
        state_manager.temperature_history["living"] = [
            (now - datetime.timedelta(minutes=10), 19.0),
            (now - datetime.timedelta(minutes=5), 21.0),
            (now, 19.5)
        ]
        
        result = state_manager.is_temperature_stable("living", minutes=5, threshold=0.5)
        assert result is False


class TestStateManagerUtilityMethods:
    """Test utility methods."""

    def test_get_zone_state_existing(self, mock_hass, sample_config, sample_zone_configs):
        """Should return zone state for existing zone."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        zone_state = state_manager.get_zone_state("living")
        assert zone_state is not None
        assert isinstance(zone_state, ZoneState)

    def test_get_zone_state_nonexistent(self, mock_hass, sample_config, sample_zone_configs):
        """Should return None for non-existent zone."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        zone_state = state_manager.get_zone_state("nonexistent")
        assert zone_state is None

    def test_get_all_zone_states(self, mock_hass, sample_config, sample_zone_configs):
        """Should return all zone states."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        all_states = state_manager.get_all_zone_states()
        assert len(all_states) == 3
        assert all(isinstance(state, ZoneState) for state in all_states.values())

    def test_is_zone_isolated_existing_zone(self, mock_hass, sample_config, sample_zone_configs):
        """Should return isolation status for existing zone."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Set zone isolation status
        state_manager.zones["baby_bed"].isolation = True
        
        assert state_manager.is_zone_isolated("baby_bed") is True
        assert state_manager.is_zone_isolated("living") is False

    def test_is_zone_isolated_nonexistent_zone(self, mock_hass, sample_config, sample_zone_configs):
        """Should return False for non-existent zone."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        assert state_manager.is_zone_isolated("nonexistent") is False


class TestStateManagerHVACModeHistory:
    """Test StateManager HVAC mode history tracking."""
    
    def test_get_time_since_last_hvac_mode_change_with_history(self, mock_hass, sample_config, sample_zone_configs):
        """Should return the time of the last HVAC mode change from Home Assistant history."""
        import datetime
        from unittest.mock import patch
        
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock history data - last_changed should be datetime objects as per debug findings
        now = datetime.datetime.now()
        old_change_time = now - datetime.timedelta(minutes=20)
        recent_change_time = now - datetime.timedelta(minutes=10)
        current_time = now - datetime.timedelta(minutes=5)
        
        # Create history with actual mode changes: dry -> heat -> heat (current)
        mock_history = [[
            {
                'state': 'dry',
                'last_changed': old_change_time  # datetime object, not string
            },
            {
                'state': 'heat',  # Mode change from dry to heat
                'last_changed': recent_change_time  # This is when heat mode started
            },
            {
                'state': 'heat',  # Still heat mode, just a temperature update
                'last_changed': current_time
            }
        ]]
        
        mock_hass.get_history.return_value = mock_history
        
        # Should return the time when heat mode started (when it changed from dry to heat)
        result = state_manager.get_time_since_last_hvac_mode_change()
        assert result == recent_change_time
    
    def test_get_time_since_last_hvac_mode_change_returns_none_with_no_history(self, mock_hass, sample_config, sample_zone_configs):
        """Should return None when no HVAC mode history is available."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock empty history
        mock_hass.get_history.return_value = []
        
        # Should return None when no history
        assert state_manager.get_time_since_last_hvac_mode_change() is None

    def test_get_time_since_last_hvac_mode_change_returns_none_with_single_entry(self, mock_hass, sample_config, sample_zone_configs):
        """Should return None when only one history entry exists (no state changes)."""
        import datetime
        
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock history with only one entry (current state, no changes)
        now = datetime.datetime.now()
        mock_history = [[
            {
                'state': 'heat',
                'last_changed': now - datetime.timedelta(minutes=5)  # datetime object, not string
            }
        ]]
        
        mock_hass.get_history.return_value = mock_history
        
        # Should return None when no state changes (only one entry)
        assert state_manager.get_time_since_last_hvac_mode_change() is None

    def test_get_time_since_last_hvac_mode_change_returns_oldest_when_no_mode_changes(self, mock_hass, sample_config, sample_zone_configs):
        """Should return oldest entry timestamp when multiple entries exist but no mode changes."""
        import datetime
        
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock history with multiple entries but same state (no mode changes)
        now = datetime.datetime.now()
        oldest_time = now - datetime.timedelta(minutes=20)
        middle_time = now - datetime.timedelta(minutes=10)
        newest_time = now - datetime.timedelta(minutes=5)
        
        mock_history = [[
            {
                'state': 'heat',
                'last_changed': oldest_time
            },
            {
                'state': 'heat',  # Same state
                'last_changed': middle_time
            },
            {
                'state': 'heat',  # Same state
                'last_changed': newest_time
            }
        ]]
        
        mock_hass.get_history.return_value = mock_history
        
        # Should return the oldest entry when no mode changes found
        assert state_manager.get_time_since_last_hvac_mode_change() == oldest_time

    def test_get_time_since_last_hvac_mode_change_uses_start_time_parameter(self, mock_hass, sample_config, sample_zone_configs):
        """Should call get_history with start_time parameter for last 2 hours."""
        import datetime
        from unittest.mock import patch
        
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock empty history to avoid processing
        mock_hass.get_history.return_value = []
        
        # Call the method
        with patch('datetime.datetime') as mock_datetime:
            mock_now = datetime.datetime(2025, 6, 20, 10, 0, 0)
            mock_datetime.now.return_value = mock_now
            mock_datetime.timedelta = datetime.timedelta  # Keep real timedelta
            
            state_manager.get_time_since_last_hvac_mode_change()
            
            # Verify get_history was called with start_time (2 hours ago)
            expected_start_time = mock_now - datetime.timedelta(hours=2)
            mock_hass.get_history.assert_called_once_with(
                entity_id=config.main_climate,
                start_time=expected_start_time
            )

    def test_get_time_since_last_hvac_mode_change_handles_errors(self, mock_hass, sample_config, sample_zone_configs):
        """Should handle errors gracefully when getting HVAC mode history."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock get_history to raise an exception
        mock_hass.get_history.side_effect = Exception("Database error")
        
        # Should return None when error occurs
        assert state_manager.get_time_since_last_hvac_mode_change() is None

    def test_get_time_since_last_hvac_mode_change_handles_timezone_aware_datetimes(self, mock_hass, sample_config, sample_zone_configs):
        """Should handle timezone-aware datetimes from history API correctly."""
        import datetime
        from datetime import timezone
        
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Create timezone-aware datetimes (like what comes from HA history API)
        now = datetime.datetime.now()
        utc_tz = timezone.utc
        old_change_time_utc = now.replace(tzinfo=utc_tz) - datetime.timedelta(minutes=20)
        recent_change_time_utc = now.replace(tzinfo=utc_tz) - datetime.timedelta(minutes=10)
        
        # Create history with timezone-aware datetimes
        mock_history = [[
            {
                'state': 'dry',
                'last_changed': old_change_time_utc  # timezone-aware datetime
            },
            {
                'state': 'heat',  # Mode change from dry to heat
                'last_changed': recent_change_time_utc  # timezone-aware datetime
            }
        ]]
        
        mock_hass.get_history.return_value = mock_history
        
        # Should return a naive datetime (timezone stripped)
        result = state_manager.get_time_since_last_hvac_mode_change()
        
        # Result should be a naive datetime (no timezone info)
        assert result is not None
        assert isinstance(result, datetime.datetime)
        assert result.tzinfo is None  # Should be naive
        
        # Should be able to compare with datetime.now() without timezone errors
        now_naive = datetime.datetime.now()
        time_diff = now_naive - result  # This should not raise timezone error
        assert isinstance(time_diff, datetime.timedelta)


@pytest.mark.edge_case
class TestStateManagerEdgeCases:
    """Test edge cases and error conditions."""

    def test_effective_target_temp_no_controller_ref(self, mock_hass, sample_config, sample_zone_configs):
        """Should use raw target temp when no controller reference."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock entity with target temperature
        def mock_get_entity(entity_id):
            entity = Mock()
            entity.get_state.return_value = "heat"
            entity.attributes = {
                "temperature": 20.0,
                "current_temperature": 19.5
            }
            return entity
        
        mock_hass.get_entity = mock_get_entity
        
        state_manager._update_single_zone("living", state_manager.zones["living"])
        
        # Should use raw target temp when no controller reference
        assert state_manager.zones["living"].target_temp == 20.0

    def test_damper_position_none_value(self, mock_hass, sample_config, sample_zone_configs):
        """Should handle None damper position."""
        config = ControllerConfig(**sample_config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock entity with None damper position
        def mock_get_entity(entity_id):
            entity = Mock()
            if "climate" in entity_id:
                entity.get_state.return_value = "heat"
                entity.attributes = {
                    "temperature": 20.0,
                    "current_temperature": 19.5
                }
            else:  # damper
                entity.attributes = {"current_position": None}
            return entity
        
        mock_hass.get_entity = mock_get_entity
        
        state_manager._update_single_zone("living", state_manager.zones["living"])
        
        # Should default to 0 when position is None
        assert state_manager.zones["living"].damper_position == 0