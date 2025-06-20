"""
Tests for temperature restoration functionality in Smart Aircon Controller V2.
Tests the integration between the robust temperature setting and restoration process.
"""
import pytest
from unittest.mock import Mock, patch
from smart_aircon_controller.smart_aircon_controller import SmartAirconController, Executor, StateManager, ControllerConfig


class TestTemperatureRestoration:
    """Test temperature restoration functionality with retry mechanism."""
    
    def test_restore_zone_targets_uses_robust_setting(self, mock_hass, sample_config, sample_zone_configs):
        """Should use the robust temperature setting method when restoring temperatures."""
        # Create a mock controller that has all the necessary components
        controller = Mock()
        controller.log = Mock()
        controller.get_state = Mock()
        
        # Mock state manager with active zones
        controller.state_manager = Mock()
        controller.state_manager.zones = {
            'living': Mock(is_active=True, entity_id='climate.living'),
            'master_bed': Mock(is_active=True, entity_id='climate.master_bed'),
            'baby_bed': Mock(is_active=False, entity_id='climate.baby_bed'),
        }
        
        # Mock executor with our new retry method
        controller.executor = Mock()
        controller.executor.set_zone_temperature_with_retry = Mock()
        
        # Mock sensor states (stored target temperatures)
        def mock_get_state(entity_id):
            if entity_id == "sensor.smart_aircon_living_target_temp":
                return "22.0"
            elif entity_id == "sensor.smart_aircon_master_bed_target_temp":
                return "20.5"
            return "unavailable"
        
        controller.get_state.side_effect = mock_get_state
        
        # Get the actual method from the real class and bind it to our mock
        from smart_aircon_controller.smart_aircon_controller import SmartAirconController
        restore_method = SmartAirconController._restore_zone_targets_from_sensors
        
        # Call the temperature restoration method
        restore_method(controller)
        
        # Verify the robust temperature setting method was called for each active zone
        actual_calls = controller.executor.set_zone_temperature_with_retry.call_args_list
        assert len(actual_calls) == 2
        
        # Check that the correct parameters were passed (entity_id and temperature)
        called_args = [(call[0][0], call[0][1]) for call in actual_calls]
        
        expected_calls = [
            ('climate.living', 22.0),
            ('climate.master_bed', 20.5),
        ]
        
        # Sort both lists to ensure order doesn't matter
        called_args.sort()
        expected_calls.sort()
        
        assert called_args == expected_calls
    
    def test_restore_zone_targets_handles_missing_sensors(self, mock_hass, sample_config, sample_zone_configs):
        """Should handle missing sensor data gracefully."""
        # Create a mock controller
        controller = Mock()
        controller.log = Mock()
        controller.get_state = Mock()
        
        # Mock state manager with active zones
        controller.state_manager = Mock()
        controller.state_manager.zones = {
            'living': Mock(is_active=True, entity_id='climate.living'),
            'master_bed': Mock(is_active=True, entity_id='climate.master_bed'),
        }
        
        # Mock executor
        controller.executor = Mock()
        controller.executor.set_zone_temperature_with_retry = Mock()
        
        # Mock sensor states - all unavailable
        controller.get_state.return_value = "unavailable"
        
        # Get the actual method from the real class and bind it to our mock
        from smart_aircon_controller.smart_aircon_controller import SmartAirconController
        restore_method = SmartAirconController._restore_zone_targets_from_sensors
        
        # Should not crash when sensors are unavailable
        restore_method(controller)
        
        # Should not have called temperature setting since no valid data
        controller.executor.set_zone_temperature_with_retry.assert_not_called()
    
    def test_restore_zone_targets_only_affects_active_zones(self, mock_hass, sample_config, sample_zone_configs):
        """Should only restore temperatures for active zones."""
        # Create a mock controller
        controller = Mock()
        controller.log = Mock()
        controller.get_state = Mock()
        
        # Mock state manager with mixed active/inactive zones
        controller.state_manager = Mock()
        controller.state_manager.zones = {
            'living': Mock(is_active=True, entity_id='climate.living'),
            'master_bed': Mock(is_active=False, entity_id='climate.master_bed'),  # Inactive
            'baby_bed': Mock(is_active=True, entity_id='climate.baby_bed'),
        }
        
        # Mock executor
        controller.executor = Mock()
        controller.executor.set_zone_temperature_with_retry = Mock()
        
        # Mock sensor states for all zones
        def mock_get_state(entity_id):
            if "living" in entity_id:
                return "22.0"
            elif "master_bed" in entity_id:
                return "20.5"
            elif "baby_bed" in entity_id:
                return "21.0"
            return "unavailable"
        
        controller.get_state.side_effect = mock_get_state
        
        # Get the actual method from the real class and bind it to our mock
        from smart_aircon_controller.smart_aircon_controller import SmartAirconController
        restore_method = SmartAirconController._restore_zone_targets_from_sensors
        
        # Call the temperature restoration method
        restore_method(controller)
        
        # Should only call for active zones (living and baby_bed)
        assert controller.executor.set_zone_temperature_with_retry.call_count == 2
        
        # Verify it was called for the right zones
        calls = controller.executor.set_zone_temperature_with_retry.call_args_list
        called_entities = [call[0][0] for call in calls]
        
        assert 'climate.living' in called_entities
        assert 'climate.baby_bed' in called_entities
        assert 'climate.master_bed' not in called_entities 