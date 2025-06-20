"""
Tests for ConfigManager class.
"""
import pytest
from unittest.mock import Mock
from smart_aircon_controller.smart_aircon_controller import ConfigManager, ControllerConfig


class TestConfigManager:
    """Test ConfigManager initialization and functionality."""
    
    def test_initialization(self, mock_hass):
        """ConfigManager should initialize with config entities and defaults."""
        config_entities = {
            "enabled": "input_boolean.smart_ac_enabled",
            "temp_tolerance": "input_number.smart_ac_temp_tolerance",
            "smart_hvac_mode": "input_select.smart_ac_hvac_mode"
        }
        
        defaults = {
            "enabled": True,
            "temp_tolerance": 0.5,
            "smart_hvac_mode": "heat"
        }
        
        # Mock entity values for initialization
        mock_hass.get_entity.side_effect = Exception("Entity not found")
        
        config_manager = ConfigManager(mock_hass, config_entities, defaults)
        
        assert config_manager.hass == mock_hass
        assert config_manager.config_entities == config_entities
        assert config_manager.defaults == defaults
        assert config_manager.current_config is not None
        assert config_manager.last_update is not None  # Will be set after initialization

    def test_update_config_success(self, mock_hass):
        """Should update configuration from Home Assistant entities."""
        config_entities = {
            "enabled": "input_boolean.smart_ac_enabled",
            "temp_tolerance": "input_number.smart_ac_temp_tolerance",
            "smart_hvac_mode": "input_select.smart_ac_hvac_mode"
        }
        
        defaults = {
            "enabled": True,
            "temp_tolerance": 0.5,
            "smart_hvac_mode": "heat"
        }
        
        # Mock entity responses for initialization and update
        def mock_get_entity(entity_id):
            entity = Mock()
            entity.get_state.side_effect = lambda: {
                "input_boolean.smart_ac_enabled": "on",
                "input_number.smart_ac_temp_tolerance": "0.7",
                "input_select.smart_ac_hvac_mode": "cool"
            }.get(entity_id, None)
            return entity
        
        mock_hass.get_entity = mock_get_entity
        
        config_manager = ConfigManager(mock_hass, config_entities, defaults)
        
        # Second call to update_config should detect changes from initialization
        # Reset the config to force a change
        config_manager.current_config.enabled = False
        config_manager.current_config.temp_tolerance = 0.1
        config_manager.current_config.smart_hvac_mode = "heat"
        
        result = config_manager.update_config()
        
        assert result is True
        assert config_manager.current_config.enabled is True
        assert config_manager.current_config.temp_tolerance == 0.7
        assert config_manager.current_config.smart_hvac_mode == "cool"
        assert config_manager.last_update is not None

    def test_update_config_with_entity_unavailable(self, mock_hass):
        """Should use defaults when entities are unavailable."""
        config_entities = {
            "enabled": "input_boolean.smart_ac_enabled",
            "temp_tolerance": "input_number.smart_ac_temp_tolerance"
        }
        
        defaults = {
            "enabled": True,
            "temp_tolerance": 0.5
        }
        
        # Mock entity unavailable
        def mock_get_entity(entity_id):
            entity = Mock()
            entity.get_state.side_effect = lambda: {
                "input_boolean.smart_ac_enabled": "unavailable",
                "input_number.smart_ac_temp_tolerance": None
            }.get(entity_id, "unavailable")
            return entity
        
        mock_hass.get_entity = mock_get_entity
        
        config_manager = ConfigManager(mock_hass, config_entities, defaults)
        
        # Second call to update_config should detect changes from initialization
        # Reset the config to force a change
        config_manager.current_config.enabled = False
        config_manager.current_config.temp_tolerance = 0.1
        
        result = config_manager.update_config()
        
        assert result is True
        assert config_manager.current_config.enabled is True  # Default value
        assert config_manager.current_config.temp_tolerance == 0.5  # Default value

    def test_update_config_exception_handling(self, mock_hass):
        """Should handle exceptions gracefully and return False."""
        config_entities = {
            "enabled": "input_boolean.smart_ac_enabled"
        }
        
        defaults = {
            "enabled": True
        }
        
        # Mock exception
        mock_hass.get_state.side_effect = Exception("Entity error")
        
        config_manager = ConfigManager(mock_hass, config_entities, defaults)
        result = config_manager.update_config()
        
        assert result is False

    def test_validate_numeric_value_within_range(self, mock_hass):
        """Should return value when within valid range."""
        mock_hass.get_entity.side_effect = Exception("Entity not found")
        config_manager = ConfigManager(mock_hass, {}, {})
        
        result = config_manager._validate_numeric_value("temp_tolerance", 0.5)
        assert result == 0.5

    def test_validate_numeric_value_below_minimum(self, mock_hass):
        """Should clamp value to minimum."""
        mock_hass.get_entity.side_effect = Exception("Entity not found")
        config_manager = ConfigManager(mock_hass, {}, {})
        
        result = config_manager._validate_numeric_value("temp_tolerance", 0.05)
        assert result == 0.1

    def test_validate_numeric_value_above_maximum(self, mock_hass):
        """Should clamp value to maximum."""
        mock_hass.get_entity.side_effect = Exception("Entity not found")
        config_manager = ConfigManager(mock_hass, {}, {})
        
        result = config_manager._validate_numeric_value("temp_tolerance", 6.0)
        assert result == 5.0

    def test_validate_numeric_value_no_validation(self, mock_hass):
        """Should return original value when no validation rule exists."""
        mock_hass.get_entity.side_effect = Exception("Entity not found")
        config_manager = ConfigManager(mock_hass, {}, {})
        
        result = config_manager._validate_numeric_value("unknown_config", 5.0)
        assert result == 5.0

    def test_get_config(self, mock_hass):
        """Should return current configuration."""
        config_manager = ConfigManager(mock_hass, {}, {})
        
        config = config_manager.get_config()
        assert isinstance(config, ControllerConfig)

    def test_should_update_first_time(self, mock_hass):
        """Should return False immediately after initialization."""
        mock_hass.get_entity.side_effect = Exception("Entity not found")
        config_manager = ConfigManager(mock_hass, {}, {})
        
        # Should return False because update was just called during initialization
        assert config_manager.should_update() is False

    def test_should_update_within_60_seconds(self, mock_hass):
        """Should return False if updated within 60 seconds."""
        import datetime
        
        config_manager = ConfigManager(mock_hass, {}, {})
        config_manager.last_update = datetime.datetime.now()
        
        assert config_manager.should_update() is False

    def test_should_update_after_60_seconds(self, mock_hass):
        """Should return True if more than 60 seconds since last update."""
        import datetime
        
        config_manager = ConfigManager(mock_hass, {}, {})
        config_manager.last_update = datetime.datetime.now() - datetime.timedelta(seconds=61)
        
        assert config_manager.should_update() is True 