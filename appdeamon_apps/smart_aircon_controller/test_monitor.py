"""
Tests for Monitor class.
"""
import pytest
import datetime
from unittest.mock import Mock
from smart_aircon_controller.smart_aircon_controller import Monitor, HVACMode, ControllerConfig, StateManager


class TestMonitor:
    """Test Monitor functionality."""
    
    def test_initialization(self, sample_config):
        """Monitor should initialize with configuration."""
        config = ControllerConfig(**sample_config)
        monitor = Monitor(config)
        
        assert monitor.config == config
        assert monitor.algorithm_start_time is None
        assert monitor.last_progress_time is None

    def test_start_monitoring(self, sample_config):
        """Should start monitoring with current timestamp."""
        config = ControllerConfig(**sample_config)
        monitor = Monitor(config)
        
        monitor.start_monitoring()
        
        assert monitor.algorithm_start_time is not None
        assert monitor.last_progress_time is not None
        assert isinstance(monitor.algorithm_start_time, datetime.datetime)

    def test_stop_monitoring(self, sample_config):
        """Should stop monitoring by clearing start time."""
        config = ControllerConfig(**sample_config)
        monitor = Monitor(config)
        
        monitor.start_monitoring()
        assert monitor.algorithm_start_time is not None
        
        monitor.stop_monitoring()
        assert monitor.algorithm_start_time is None
        assert monitor.last_progress_time is None

    def test_check_progress_not_started(self, mock_hass, sample_config, sample_zone_configs):
        """Should return True if monitoring not started."""
        config = ControllerConfig(**sample_config)
        monitor = Monitor(config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        result = monitor.check_progress(state_manager, HVACMode.HEAT)
        assert result is True

    def test_check_progress_within_timeout(self, mock_hass, sample_config, sample_zone_configs):
        """Should return True if within progress timeout."""
        config = ControllerConfig(**sample_config)
        config.progress_timeout_minutes = 15
        monitor = Monitor(config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Start monitoring recently
        monitor.start_time = datetime.datetime.now() - datetime.timedelta(minutes=5)
        
        # Mock zones making progress
        state_manager.zones["living"].is_active = True
        state_manager.zones["living"].current_temp = 19.0
        state_manager.zones["living"].target_temp = 20.0
        
        # Mock temperature history showing progress
        state_manager.temperature_history["living"] = [
            (datetime.datetime.now() - datetime.timedelta(minutes=10), 18.5),
            (datetime.datetime.now() - datetime.timedelta(minutes=5), 19.0)
        ]
        
        result = monitor.check_progress(state_manager, HVACMode.HEAT)
        assert result is True

    def test_check_progress_with_monitoring_started(self, mock_hass, sample_config, sample_zone_configs):
        """Should return True when monitoring is started and making progress."""
        config = ControllerConfig(**sample_config)
        monitor = Monitor(config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Start monitoring
        monitor.start_monitoring()
        
        # Mock zones making progress
        state_manager.zones["living"].is_active = True
        state_manager.zones["living"].current_temp = 19.5
        state_manager.zones["living"].target_temp = 20.0
        
        # Mock temperature history showing progress
        now = datetime.datetime.now()
        state_manager.temperature_history["living"] = [
            (now - datetime.timedelta(minutes=10), 19.0),
            (now - datetime.timedelta(minutes=5), 19.2),
            (now, 19.5)
        ]
        
        result = monitor.check_progress(state_manager, HVACMode.HEAT)
        assert result is True

    def test_zone_making_progress_heating(self, mock_hass, sample_config, sample_zone_configs):
        """Should detect progress for heating mode."""
        config = ControllerConfig(**sample_config)
        monitor = Monitor(config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        now = datetime.datetime.now()
        
        # Mock temperature history showing heating progress (need readings > 5 minutes ago)
        state_manager.temperature_history["living"] = [
            (now - datetime.timedelta(minutes=10), 18.5),
            (now - datetime.timedelta(minutes=6), 19.0),  # Reading from 6 minutes ago
            (now, 19.5)
        ]
        
        # Mock current zone state
        state_manager.zones["living"].current_temp = 19.6  # Show progress from 6 minutes ago
        
        result = monitor._zone_making_progress(state_manager, "living", HVACMode.HEAT, now)
        assert result is True

    def test_zone_making_progress_cooling(self, mock_hass, sample_config, sample_zone_configs):
        """Should detect progress for cooling mode."""
        config = ControllerConfig(**sample_config)
        monitor = Monitor(config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        now = datetime.datetime.now()
        
        # Mock temperature history showing cooling progress
        state_manager.temperature_history["living"] = [
            (now - datetime.timedelta(minutes=10), 25.5),
            (now - datetime.timedelta(minutes=5), 25.0),
            (now, 24.5)
        ]
        
        result = monitor._zone_making_progress(state_manager, "living", HVACMode.COOL, now)
        assert result is True

    def test_zone_not_making_progress(self, mock_hass, sample_config, sample_zone_configs):
        """Should detect when zone is not making progress."""
        config = ControllerConfig(**sample_config)
        monitor = Monitor(config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        now = datetime.datetime.now()
        
        # Mock temperature history showing no progress
        state_manager.temperature_history["living"] = [
            (now - datetime.timedelta(minutes=10), 19.0),
            (now - datetime.timedelta(minutes=5), 19.0),
            (now, 19.0)
        ]
        
        result = monitor._zone_making_progress(state_manager, "living", HVACMode.HEAT, now)
        assert result is False

    def test_should_fallback_algorithm_timeout(self, mock_hass, sample_config, sample_zone_configs):
        """Should recommend fallback when algorithm timeout exceeded."""
        config = ControllerConfig(**sample_config)
        config.algorithm_timeout_minutes = 30
        monitor = Monitor(config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock algorithm running for too long
        monitor.algorithm_start_time = datetime.datetime.now() - datetime.timedelta(minutes=35)
        
        result = monitor.should_fallback(state_manager)
        assert result is True

    def test_should_fallback_progress_timeout(self, mock_hass, sample_config, sample_zone_configs):
        """Should recommend fallback when no progress for too long."""
        config = ControllerConfig(**sample_config)
        config.progress_timeout_minutes = 15
        monitor = Monitor(config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock algorithm started recently but no progress for too long
        monitor.algorithm_start_time = datetime.datetime.now() - datetime.timedelta(minutes=10)
        monitor.last_progress_time = datetime.datetime.now() - datetime.timedelta(minutes=20)
        
        result = monitor.should_fallback(state_manager)
        assert result is True

    def test_should_not_fallback_normal_operation(self, mock_hass, sample_config, sample_zone_configs):
        """Should not recommend fallback during normal operation."""
        config = ControllerConfig(**sample_config)
        monitor = Monitor(config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock normal operation
        monitor.algorithm_start_time = datetime.datetime.now() - datetime.timedelta(minutes=10)
        state_manager.zones["living"].is_active = True
        
        result = monitor.should_fallback(state_manager)
        assert result is False 