"""
Tests for state transition edge cases in Smart Aircon Controller V2.
Covers scenarios like enabling/disabling during active HVAC operation,
Home Assistant restarts, and other critical state transitions.
"""
import pytest
from unittest.mock import Mock, patch
import datetime
from smart_aircon_controller import StateManager, DecisionEngine, ConfigManager, HVACMode, ControllerConfig


class TestConfigManagerEnableDisableTransitions:
    """Test config manager behavior during enable/disable transitions."""
    
    def test_config_manager_handles_enable_disable_transitions(self, mock_hass, sample_config):
        """Should handle enable/disable transitions via HA entities."""
        config_entities = {"enabled": "input_boolean.smart_aircon_enabled"}
        config_defaults = {"enabled": True}
        
        # Mock entity returning different values over time
        entity = Mock()
        entity.get_state.return_value = "on"  # Start with enabled
        mock_hass.get_entity.return_value = entity
        
        config_manager = ConfigManager(mock_hass, config_entities, config_defaults)
        
        # Initially enabled (from constructor)
        config = config_manager.get_config()
        assert config.enabled == True
        
        # Then disabled
        entity.get_state.return_value = "off"
        config_manager.update_config()
        config = config_manager.get_config()
        assert config.enabled == False
        
        # Then enabled again
        entity.get_state.return_value = "on"
        config_manager.update_config()
        config = config_manager.get_config()
        assert config.enabled == True
        
        # Should handle rapid transitions
        for state in ["off", "on", "off", "on"]:
            entity.get_state.return_value = state
            config_manager.update_config()
            config = config_manager.get_config()
            expected = state == "on"
            assert config.enabled == expected
    
    def test_config_manager_handles_cooling_mode_transitions(self, mock_hass, sample_config):
        """Should handle mode transitions between heating and cooling."""
        config_entities = {"smart_hvac_mode": "input_select.smart_aircon_mode"}
        config_defaults = {"smart_hvac_mode": "heat"}
        
        entity = Mock()
        entity.get_state.return_value = "heat"  # Start with heat mode
        mock_hass.get_entity.return_value = entity
        
        config_manager = ConfigManager(mock_hass, config_entities, config_defaults)
        
        # Initially heating mode
        config = config_manager.get_config()
        assert config.smart_hvac_mode == "heat"
        
        # Switch to cooling mode
        entity.get_state.return_value = "cool"
        config_manager.update_config()
        config = config_manager.get_config()
        assert config.smart_hvac_mode == "cool"


class TestDecisionEngineStateTransitions:
    """Test decision engine behavior during state transitions."""
    
    def test_decision_engine_mode_transitions_during_execution(self, sample_config):
        """Should handle mode changes during algorithm execution."""
        config = ControllerConfig(**sample_config)
        decision_engine = DecisionEngine(config)
        
        # Test switching from heat to cool mode
        heating_config = ControllerConfig(**sample_config)
        heating_config.smart_hvac_mode = "heat"
        
        cooling_config = ControllerConfig(**sample_config)
        cooling_config.smart_hvac_mode = "cool"
        
        # Verify idle mode changes with smart_hvac_mode
        assert decision_engine.get_idle_mode("heat") == HVACMode.DRY
        assert decision_engine.get_idle_mode("cool") == HVACMode.FAN
    
    def test_decision_engine_handles_partial_zone_satisfaction(self, sample_config):
        """Should handle scenarios where some zones are satisfied, others still need attention."""
        config = ControllerConfig(**sample_config)
        decision_engine = DecisionEngine(config)
        
        # Mock state manager with partial satisfaction
        state_manager = Mock()
        
        # In heating mode: some zones still need heating, others are satisfied
        state_manager.get_zones_needing_heating.return_value = ["living"]  # Still needs heat
        state_manager.get_zones_needing_cooling.return_value = []  # No cooling needs in heat mode
        state_manager.all_zones_satisfied.return_value = False  # Not all satisfied yet
        
        # Should continue heating until all zones satisfied
        config.smart_hvac_mode = "heat"
        target_mode = decision_engine.get_target_hvac_mode(state_manager)
        assert target_mode == HVACMode.HEAT
        
        # In cooling mode: some zones still need cooling, others are satisfied  
        state_manager.get_zones_needing_heating.return_value = []  # No heating needs in cool mode
        state_manager.get_zones_needing_cooling.return_value = ["master_bed"]  # Still needs cooling
        state_manager.all_zones_satisfied.return_value = False  # Not all satisfied yet
        
        config.smart_hvac_mode = "cool"
        target_mode = decision_engine.get_target_hvac_mode(state_manager)
        assert target_mode == HVACMode.COOL


class TestStateManagerEntityFailures:
    """Test state manager behavior during entity failures."""
    
    def test_state_manager_handles_unavailable_entities_during_startup(self, mock_hass, sample_config, sample_zone_configs):
        """Should handle unavailable entities during HA startup gracefully."""
        config = ControllerConfig(**sample_config)
        
        # Mock entities as unavailable (common during HA startup)
        def mock_get_entity(entity_id):
            entity = Mock()
            if "living_2" in entity_id:
                entity.get_state.return_value = "unavailable"
                entity.attributes = {}
            else:
                entity.get_state.return_value = "heat" 
                entity.attributes = {"temperature": 20.0, "current_temperature": 19.0, "current_position": 50}
            return entity
        
        mock_hass.get_entity.side_effect = mock_get_entity
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Should initialize without errors
        assert len(state_manager.zones) == len(sample_zone_configs)
        
        # Update should handle unavailable entities gracefully without crashing
        try:
            state_manager.update_all_zones()
            # Should complete without exceptions
            assert True
        except Exception as e:
            # If there's an exception, it should be handled gracefully
            assert False, f"StateManager should handle unavailable entities gracefully: {e}"
    
    def test_state_manager_handles_stuck_dampers(self, mock_hass, sample_config, sample_zone_configs):
        """Should detect when dampers don't respond to position commands."""
        config = ControllerConfig(**sample_config)
        
        # Mock damper entity that's stuck at one position
        def mock_get_entity(entity_id):
            entity = Mock()
            if "damper" in entity_id:
                entity.get_state.return_value = "open"
                entity.attributes = {"current_position": 0}  # Stuck closed
            else:
                entity.get_state.return_value = "heat"
                entity.attributes = {"temperature": 20.0, "current_temperature": 19.0}
            return entity
        
        mock_hass.get_entity.side_effect = mock_get_entity
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.update_all_zones()
        
        # Should detect all dampers are low/stuck
        assert state_manager.all_dampers_low() == True
    
    def test_state_manager_handles_sensor_failures(self, mock_hass, sample_config, sample_zone_configs):
        """Should handle temperature sensor failures gracefully."""
        config = ControllerConfig(**sample_config)
        
        # Mock climate entity with missing temperature
        def mock_get_entity(entity_id):
            entity = Mock()
            if "climate" in entity_id:
                entity.get_state.return_value = "heat"
                entity.attributes = {"temperature": 20.0}  # Missing current_temperature
            else:
                entity.get_state.return_value = "open"
                entity.attributes = {"current_position": 50}
            return entity
        
        mock_hass.get_entity.side_effect = mock_get_entity
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.update_all_zones()
        
        # Should handle missing temperature data gracefully
        zones_needing_heating = state_manager.get_zones_needing_heating()
        assert isinstance(zones_needing_heating, list)


class TestConfigManagerFailureScenarios:
    """Test config manager behavior during various failure scenarios."""
    
    def test_config_manager_handles_unavailable_entities_during_restart(self, mock_hass, sample_config):
        """Should handle unavailable config entities during HA restart gracefully."""
        config_entities = {
            "enabled": "input_boolean.smart_aircon_enabled",
            "temp_tolerance": "input_number.smart_aircon_temp_tolerance"
        }
        config_defaults = {"enabled": True, "temp_tolerance": 0.5}
        
        # Mock entities being unavailable during HA startup
        def mock_get_entity(entity_id):
            entity = Mock()
            if "smart_aircon_enabled" in entity_id:
                entity.get_state.return_value = "unavailable"  # HA still starting
            elif "temp_tolerance" in entity_id:
                entity.get_state.return_value = "unknown"  # Entity not ready
            return entity
        
        mock_hass.get_entity.side_effect = mock_get_entity
        
        # Create config manager
        config_manager = ConfigManager(mock_hass, config_entities, config_defaults)
        
        # Should use fallback values when entities unavailable
        config = config_manager.get_config()
        assert config.enabled == True  # From defaults
        assert config.temp_tolerance == 0.5  # From defaults
        
        # Should log warnings about unavailable entities
        assert mock_hass.log.call_count > 0
        warning_calls = [call for call in mock_hass.log.call_args_list if "WARNING" in str(call[0][0])]
        assert len(warning_calls) >= 2  # One for each unavailable entity
    
    def test_network_timeout_during_entity_updates(self, mock_hass, sample_config):
        """Should handle network timeouts gracefully during entity updates."""
        config_entities = {"enabled": "input_boolean.smart_aircon_enabled"}
        config_defaults = {"enabled": True}
        
        # Mock network timeout
        def timeout_side_effect(*args, **kwargs):
            raise TimeoutError("Network timeout")
        
        mock_hass.get_entity.side_effect = timeout_side_effect
        
        # Should handle timeout gracefully
        config_manager = ConfigManager(mock_hass, config_entities, config_defaults)
        
        # Should use fallback values and log error
        config = config_manager.get_config()
        assert config.enabled == True  # Fallback value
        
        # Should log error
        error_calls = [call for call in mock_hass.log.call_args_list if "Error reading config entity" in str(call)]
        assert len(error_calls) > 0
    
    def test_invalid_config_values_clamping(self, mock_hass, sample_config):
        """Should clamp invalid configuration values to safe ranges."""
        config_entities = {
            "temp_tolerance": "input_number.smart_aircon_temp_tolerance",
            "primary_damper_percent": "input_number.smart_aircon_primary_damper"
        }
        config_defaults = {"temp_tolerance": 0.5, "primary_damper_percent": 50}
        
        # Mock entities returning invalid values
        def mock_get_entity(entity_id):
            entity = Mock()
            if "temp_tolerance" in entity_id:
                entity.get_state.return_value = "10.0"  # Too high (max 5.0)
            elif "primary_damper" in entity_id:
                entity.get_state.return_value = "10"  # Too low (min 30)
            return entity
        
        mock_hass.get_entity.side_effect = mock_get_entity
        
        config_manager = ConfigManager(mock_hass, config_entities, config_defaults)
        config = config_manager.get_config()
        
        # Should clamp values to safe ranges
        assert config.temp_tolerance == 5.0  # Clamped to max
        assert config.primary_damper_percent == 30  # Clamped to min
        
        # Should log warnings about clamping
        warning_calls = [call for call in mock_hass.log.call_args_list if "WARNING" in str(call[0][0])]
        assert len(warning_calls) >= 2


class TestDecisionEngineEdgeCases:
    """Test decision engine behavior in edge case scenarios."""
    
    def test_decision_engine_handles_extreme_temperature_differences(self, sample_config):
        """Should handle scenarios with extreme temperature differences between zones."""
        config = ControllerConfig(**sample_config)
        decision_engine = DecisionEngine(config)
        
        # Mock state manager with extreme temperature differences
        state_manager = Mock()
        
        # One zone extremely cold, others comfortable
        state_manager.get_zones_needing_heating.return_value = ["living"]  # 10°C below target
        state_manager.get_zones_needing_cooling.return_value = []
        state_manager.all_zones_satisfied.return_value = False
        
        # Should still activate heating for the cold zone
        config.smart_hvac_mode = "heat"
        target_mode = decision_engine.get_target_hvac_mode(state_manager)
        assert target_mode == HVACMode.HEAT
    
    def test_decision_engine_handles_rapid_satisfaction_changes(self, sample_config):
        """Should handle rapid changes between satisfied and unsatisfied states."""
        config = ControllerConfig(**sample_config)
        decision_engine = DecisionEngine(config)
        
        state_manager = Mock()
        
        # Simulate rapid fluctuations in heating mode: satisfied/unsatisfied
        config.smart_hvac_mode = "heat"
        state_manager.get_zones_needing_cooling.return_value = []  # Never need cooling in heat mode
        
        for i in range(5):
            if i % 2 == 0:
                # Some zones still need heating
                state_manager.get_zones_needing_heating.return_value = ["living"]
                state_manager.all_zones_satisfied.return_value = False
                expected_mode = HVACMode.HEAT
            else:
                # All zones temporarily satisfied
                state_manager.get_zones_needing_heating.return_value = []
                state_manager.all_zones_satisfied.return_value = True
                expected_mode = HVACMode.DRY  # Should go to idle
            
            target_mode = decision_engine.get_target_hvac_mode(state_manager)
            assert target_mode == expected_mode


@pytest.mark.edge_case
class TestIntegrationEdgeCases:
    """Test integration scenarios between components."""
    
    def test_state_manager_and_decision_engine_coordination(self, mock_hass, sample_config, sample_zone_configs):
        """Should coordinate properly between state manager and decision engine."""
        config = ControllerConfig(**sample_config)
        
        # Setup state manager with real zone data
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        decision_engine = DecisionEngine(config)
        
        # Mock entities for consistent testing
        def mock_get_entity(entity_id):
            entity = Mock()
            if "climate" in entity_id:
                entity.get_state.return_value = "heat"
                entity.attributes = {"temperature": 20.0, "current_temperature": 18.0}  # Needs heating
            else:
                entity.get_state.return_value = "open"
                entity.attributes = {"current_position": 50}
            return entity
        
        mock_hass.get_entity.side_effect = mock_get_entity
        
        # Update state and make decision
        state_manager.update_all_zones()
        zones_needing_heating = state_manager.get_zones_needing_heating()
        
        # Decision engine should respond appropriately
        config.smart_hvac_mode = "heat"
        target_mode = decision_engine.get_target_hvac_mode(state_manager)
        
        # Should activate heating when zones need it
        if zones_needing_heating:
            assert target_mode == HVACMode.HEAT
        else:
            assert target_mode == HVACMode.DRY
    
    def test_config_manager_and_decision_engine_dynamic_updates(self, mock_hass, sample_config):
        """Should handle dynamic configuration changes affecting decisions."""
        config_entities = {"smart_hvac_mode": "input_select.smart_aircon_mode"}
        config_defaults = {"smart_hvac_mode": "heat"}
        
        entity = Mock()
        mock_hass.get_entity.return_value = entity
        
        config_manager = ConfigManager(mock_hass, config_entities, config_defaults)
        
        # Initially in heat mode
        entity.get_state.return_value = "heat"
        config = config_manager.get_config()
        decision_engine = DecisionEngine(config)
        
        assert decision_engine.get_idle_mode("heat") == HVACMode.DRY
        
        # Switch to cool mode
        entity.get_state.return_value = "cool"
        config = config_manager.get_config()
        decision_engine = DecisionEngine(config)  # In real implementation, config would be updated
        
        assert decision_engine.get_idle_mode("cool") == HVACMode.FAN