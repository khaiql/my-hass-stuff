"""
Tests for no active zones behavior.
"""
import pytest
from unittest.mock import Mock, patch
from smart_aircon_controller.smart_aircon_controller import (
    SmartAirconController, 
    ControllerConfig, 
    StateManager, 
    DecisionEngine,
    Executor,
    Monitor,
    HVACMode
)


class TestNoActiveZonesBehavior:
    """Test controller behavior when no zones are active."""

    @pytest.fixture
    def mock_controller(self, mock_hass, sample_config, sample_zone_configs):
        """Create a mock controller for testing."""
        controller = Mock(spec=SmartAirconController)
        controller.static_config = ControllerConfig(**sample_config)
        controller.algorithm_active = False
        controller.current_algorithm_mode = None
        
        # Create real components
        config = ControllerConfig(**sample_config)
        controller.state_manager = StateManager(mock_hass, config, sample_zone_configs)
        controller.decision_engine = DecisionEngine(config)
        controller.executor = Executor(mock_hass, config, config)
        controller.monitor = Monitor(config)
        
        # Mock logging
        controller.log = Mock()
        
        return controller

    def test_no_active_zones_returns_empty_list(self, mock_controller):
        """Should return empty list when no zones are active."""
        # Set all zones inactive
        for zone in mock_controller.state_manager.zones.values():
            zone.is_active = False
        
        active_zones = mock_controller.state_manager.get_active_zones()
        assert active_zones == []

    def test_no_active_zones_should_not_activate_heating(self, mock_controller):
        """Should not activate heating when no zones are active."""
        # Set all zones inactive
        for zone in mock_controller.state_manager.zones.values():
            zone.is_active = False
        
        should_activate = mock_controller.decision_engine.should_activate_heating(
            mock_controller.state_manager
        )
        assert should_activate is False

    def test_no_active_zones_should_not_activate_cooling(self, mock_controller):
        """Should not activate cooling when no zones are active."""
        # Set all zones inactive
        for zone in mock_controller.state_manager.zones.values():
            zone.is_active = False
        
        should_activate = mock_controller.decision_engine.should_activate_cooling(
            mock_controller.state_manager
        )
        assert should_activate is False

    def test_no_active_zones_returns_idle_target_mode(self, mock_controller):
        """Should return idle mode when no zones are active."""
        # Set all zones inactive
        for zone in mock_controller.state_manager.zones.values():
            zone.is_active = False
        
        # Test heating mode -> DRY
        mock_controller.decision_engine.config.smart_hvac_mode = "heat"
        target_mode = mock_controller.decision_engine.get_target_hvac_mode(
            mock_controller.state_manager
        )
        assert target_mode == HVACMode.DRY
        
        # Test cooling mode -> FAN
        mock_controller.decision_engine.config.smart_hvac_mode = "cool"
        target_mode = mock_controller.decision_engine.get_target_hvac_mode(
            mock_controller.state_manager
        )
        assert target_mode == HVACMode.FAN

    def test_no_active_zones_damper_calculation_all_zero(self, mock_controller):
        """Should set all dampers to 0% when no zones are active."""
        # Set all zones inactive
        for zone in mock_controller.state_manager.zones.values():
            zone.is_active = False
        
        positions = mock_controller.decision_engine.calculate_damper_positions(
            mock_controller.state_manager, [], HVACMode.HEAT
        )
        
        # All dampers should be 0% for inactive zones
        for zone_name, position in positions.items():
            assert position == 0

    def test_no_active_zones_set_minimum_dampers_does_nothing(self, mock_controller):
        """Should not set any dampers when no zones are active."""
        # Set all zones inactive
        for zone in mock_controller.state_manager.zones.values():
            zone.is_active = False
        
        # Mock the executor's hass API
        mock_controller.executor.hass.call_service = Mock()
        
        mock_controller.executor.set_minimum_dampers(mock_controller.state_manager)
        
        # Should not make any service calls
        mock_controller.executor.hass.call_service.assert_not_called()

    def test_periodic_check_exits_early_when_no_active_zones(self, mock_hass, sample_config, sample_zone_configs):
        """Should exit early from periodic check when no zones are active."""
        from smart_aircon_controller.smart_aircon_controller import SmartAirconController
        
        # Create a real controller instance for testing
        controller = Mock(spec=SmartAirconController)
        controller.static_config = ControllerConfig(**sample_config)
        controller.algorithm_active = False
        controller.current_algorithm_mode = None
        
        # Create real state manager
        config = ControllerConfig(**sample_config)
        controller.state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Set all zones inactive
        for zone in controller.state_manager.zones.values():
            zone.is_active = False
        
        # Mock the periodic check method
        controller.log = Mock()
        controller.state_manager.update_all_zones = Mock()
        controller.state_manager.update_hvac_mode = Mock()
        
        # Import and bind the actual periodic check method
        from smart_aircon_controller.smart_aircon_controller import SmartAirconController
        controller._periodic_check = SmartAirconController._periodic_check.__get__(controller)
        
        # Mock config manager
        controller.config_manager = Mock()
        controller.config_manager.should_update.return_value = False
        controller.config_manager.get_config.return_value = config
        
        # Call periodic check
        controller._periodic_check({})
        
        # Verify it logged the no active zones message
        controller.log.assert_any_call("ℹ️  No active zones detected - automation will do nothing (zones not managed)")
        controller.log.assert_any_call("=== AUTOMATION IDLE: NO ZONES TO MANAGE ===")
        
        # Verify it didn't try to process further (no target mode logging)
        log_calls = [call.args[0] for call in controller.log.call_args_list]
        assert not any("Target HVAC mode:" in call for call in log_calls) 