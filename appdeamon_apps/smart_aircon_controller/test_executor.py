"""
Tests for Executor class.
"""
import pytest
from unittest.mock import Mock
from smart_aircon_controller.smart_aircon_controller import Executor, HVACMode, ControllerConfig, StateManager


class TestExecutor:
    """Test Executor functionality."""
    
    def test_initialization(self, mock_hass, sample_config):
        """Executor should initialize with HASS API and configuration."""
        config = ControllerConfig(**sample_config)
        executor = Executor(mock_hass, config, config)
        
        assert executor.hass == mock_hass
        assert executor.config == config

    def test_set_hvac_mode_success(self, mock_hass, sample_config):
        """Should set HVAC mode via climate service call."""
        config = ControllerConfig(**sample_config)
        executor = Executor(mock_hass, config, config)
        
        executor.set_hvac_mode(HVACMode.HEAT)
        
        mock_hass.call_service.assert_called_once_with(
            "climate/set_hvac_mode",
            entity_id=config.main_climate,
            hvac_mode="heat"
        )

    def test_set_hvac_mode_exception_handling(self, mock_hass, sample_config):
        """Should handle exceptions when setting HVAC mode."""
        config = ControllerConfig(**sample_config)
        executor = Executor(mock_hass, config, config)
        
        mock_hass.call_service.side_effect = Exception("Service call failed")
        
        # Should not raise exception
        executor.set_hvac_mode(HVACMode.HEAT)

    def test_set_damper_positions_success(self, mock_hass, sample_config, sample_zone_configs):
        """Should set damper positions for specified zones."""
        config = ControllerConfig(**sample_config)
        executor = Executor(mock_hass, config, config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        positions = {
            "living": 50,
            "master_bed": 30
        }
        
        executor.set_damper_positions(positions, state_manager)
        
        # Should call service for each zone
        assert mock_hass.call_service.call_count == 2
        
        # Check specific calls
        calls = mock_hass.call_service.call_args_list
        assert any("cover/set_cover_position" in str(call) for call in calls)

    def test_set_damper_positions_exception_handling(self, mock_hass, sample_config, sample_zone_configs):
        """Should handle exceptions when setting damper positions."""
        config = ControllerConfig(**sample_config)
        executor = Executor(mock_hass, config, config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        mock_hass.call_service.side_effect = Exception("Service call failed")
        
        positions = {
            "living": 50
        }
        
        # Should not raise exception
        executor.set_damper_positions(positions, state_manager)

    def test_set_minimum_dampers(self, mock_hass, sample_config, sample_zone_configs):
        """Should set minimum damper positions for active zones."""
        config = ControllerConfig(**sample_config)
        executor = Executor(mock_hass, config, config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock some active zones
        state_manager.zones["living"].is_active = True
        state_manager.zones["master_bed"].is_active = True
        state_manager.zones["baby_bed"].is_active = False
        
        executor.set_minimum_dampers(state_manager)
        
        # Should call service for active zones only
        assert mock_hass.call_service.call_count == 2  # living and master_bed 