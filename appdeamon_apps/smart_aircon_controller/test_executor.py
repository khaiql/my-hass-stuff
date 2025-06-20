"""
Tests for Executor class.
"""
import pytest
from unittest.mock import Mock, call
from smart_aircon_controller.smart_aircon_controller import Executor, HVACMode, ControllerConfig, StateManager
import time


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

    # New tests for temperature setting with retry
    def test_set_zone_temperature_with_retry_success_first_attempt(self, mock_hass, sample_config):
        """Should set zone temperature successfully on first attempt."""
        config = ControllerConfig(**sample_config)
        executor = Executor(mock_hass, config, config)
        
        # Mock entity with temperature attribute
        mock_entity = Mock()
        mock_entity.attributes = {"temperature": 22.0}
        mock_hass.get_entity.return_value = mock_entity
        
        result = executor.set_zone_temperature_with_retry("climate.living", 22.0)
        
        assert result is True
        mock_hass.call_service.assert_called_once_with(
            "climate/set_temperature",
            entity_id="climate.living",
            temperature=22.0
        )

    def test_set_zone_temperature_with_retry_callback_success(self, mock_hass, sample_config):
        """Should call callback with success when using async mode."""
        config = ControllerConfig(**sample_config)
        executor = Executor(mock_hass, config, config)
        
        # Mock entity with temperature attribute
        mock_entity = Mock()
        mock_entity.attributes = {"temperature": 22.0}
        mock_hass.get_entity.return_value = mock_entity
        
        callback_mock = Mock()
        executor.set_zone_temperature_with_retry("climate.living", 22.0, callback=callback_mock)
        
        # Verify initial call was made
        mock_hass.call_service.assert_called_once_with(
            "climate/set_temperature",
            entity_id="climate.living",
            temperature=22.0
        )
        
        # Verify verification callback was scheduled
        mock_hass.run_in.assert_called_once()
        assert mock_hass.run_in.call_args[0][0] == executor._verify_temperature_setting

    def test_set_zone_temperature_with_retry_tolerance(self, mock_hass, sample_config):
        """Should consider temperatures within tolerance as success."""
        config = ControllerConfig(**sample_config)
        executor = Executor(mock_hass, config, config)
        
        # Mock entity with temperature close to target (within 0.1°C tolerance)
        mock_entity = Mock()
        mock_entity.attributes = {"temperature": 22.05}  # Close to 22.0
        mock_hass.get_entity.return_value = mock_entity
        
        result = executor.set_zone_temperature_with_retry("climate.living", 22.0)
        
        assert result is True
        mock_hass.call_service.assert_called_once()  # Only one attempt needed

    def test_set_zone_temperature_with_retry_entity_unavailable(self, mock_hass, sample_config):
        """Should handle unavailable entity gracefully."""
        config = ControllerConfig(**sample_config)
        executor = Executor(mock_hass, config, config)
        
        # Mock unavailable entity
        mock_entity = Mock()
        mock_entity.attributes = {}  # No temperature attribute
        mock_hass.get_entity.return_value = mock_entity
        
        result = executor.set_zone_temperature_with_retry("climate.living", 22.0)
        
        assert result is False
        # Should still try to set temperature
        mock_hass.call_service.assert_called_with(
            "climate/set_temperature",
            entity_id="climate.living",
            temperature=22.0
        )

    def test_set_zone_temperature_with_retry_dry_run_mode(self, mock_hass, sample_config):
        """Should log actions in dry run mode without calling services."""
        config = ControllerConfig(**sample_config)
        config.dry_run = True
        executor = Executor(mock_hass, config, config)
        
        result = executor.set_zone_temperature_with_retry("climate.living", 22.0)
        
        assert result is True
        mock_hass.call_service.assert_not_called()

    def test_set_zone_temperature_with_retry_dry_run_with_callback(self, mock_hass, sample_config):
        """Should call callback with success in dry run mode."""
        config = ControllerConfig(**sample_config)
        config.dry_run = True
        executor = Executor(mock_hass, config, config)
        
        callback_mock = Mock()
        result = executor.set_zone_temperature_with_retry("climate.living", 22.0, callback=callback_mock)
        
        assert result is True
        callback_mock.assert_called_once_with(True)
        mock_hass.call_service.assert_not_called()

    def test_verify_temperature_setting_success(self, mock_hass, sample_config):
        """Should verify temperature was set correctly and call callback."""
        config = ControllerConfig(**sample_config)
        executor = Executor(mock_hass, config, config)
        
        # Mock entity with correct temperature
        mock_entity = Mock()
        mock_entity.attributes = {"temperature": 22.0}
        mock_hass.get_entity.return_value = mock_entity
        
        callback_mock = Mock()
        retry_context = {
            'entity_id': 'climate.living',
            'target_temp': 22.0,
            'callback': callback_mock,
            'tolerance': 0.1,
            'current_attempt': 1,
            'max_retries': 3
        }
        
        executor._verify_temperature_setting({'retry_context': retry_context})
        
        callback_mock.assert_called_once_with(True)

    def test_verify_temperature_setting_retry_needed(self, mock_hass, sample_config):
        """Should schedule retry when temperature not set correctly."""
        config = ControllerConfig(**sample_config)
        executor = Executor(mock_hass, config, config)
        
        # Mock entity with wrong temperature
        mock_entity = Mock()
        mock_entity.attributes = {"temperature": 20.0}  # Wrong temperature
        mock_hass.get_entity.return_value = mock_entity
        
        callback_mock = Mock()
        retry_context = {
            'entity_id': 'climate.living',
            'target_temp': 22.0,
            'callback': callback_mock,
            'tolerance': 0.1,
            'current_attempt': 1,
            'max_retries': 3,
            'wait_seconds': 2.0
        }
        
        executor._verify_temperature_setting({'retry_context': retry_context})
        
        # Should schedule retry, not call callback yet
        callback_mock.assert_not_called()
        mock_hass.run_in.assert_called_once()
        
        # Verify retry context was updated
        assert retry_context['current_attempt'] == 2 