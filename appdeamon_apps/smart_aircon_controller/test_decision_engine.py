"""
Tests for DecisionEngine class.
Following TDD approach - comprehensive tests for decision logic.
"""
import pytest
from unittest.mock import Mock
from smart_aircon_controller import DecisionEngine, StateManager, HVACMode, ControllerConfig


class TestDecisionEngineInitialization:
    """Test DecisionEngine initialization."""
    
    def test_initialization_with_config(self, sample_config):
        """DecisionEngine should initialize with configuration."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        assert engine.config == config


class TestAutomaticIdleModeLogic:
    """Test automatic idle mode determination."""
    
    def test_get_idle_mode_heat_returns_dry(self, sample_config):
        """Should return DRY for heat mode."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        assert engine.get_idle_mode("heat") == HVACMode.DRY
    
    def test_get_idle_mode_cool_returns_fan(self, sample_config):
        """Should return FAN for cool mode."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        assert engine.get_idle_mode("cool") == HVACMode.FAN
    
    def test_get_idle_mode_unknown_returns_dry_fallback(self, sample_config):
        """Should return DRY for unknown modes as fallback."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        assert engine.get_idle_mode("unknown") == HVACMode.DRY
        assert engine.get_idle_mode("") == HVACMode.DRY
        assert engine.get_idle_mode("invalid") == HVACMode.DRY


class TestHeatingDecisions:
    """Test heating mode decision logic."""
    
    def test_should_activate_heating_when_zones_need_heat(self, mock_hass, sample_config, sample_zone_configs):
        """Should activate heating when zones need heat and mode is heat."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "heat"
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock zones needing heat
        state_manager.get_zones_needing_heating = Mock(return_value=["living", "baby_bed"])
        
        assert engine.should_activate_heating(state_manager) is True
    
    def test_should_not_activate_heating_when_no_zones_need_heat(self, mock_hass, sample_config, sample_zone_configs):
        """Should not activate heating when no zones need heat."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "heat"
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.get_zones_needing_heating = Mock(return_value=[])
        
        assert engine.should_activate_heating(state_manager) is False
    
    def test_should_not_activate_heating_when_mode_is_cooling(self, mock_hass, sample_config, sample_zone_configs):
        """Should not activate heating when smart mode is cooling."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "cool"
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.get_zones_needing_heating = Mock(return_value=["living"])
        
        assert engine.should_activate_heating(state_manager) is False


class TestCoolingDecisions:
    """Test cooling mode decision logic."""
    
    def test_should_activate_cooling_when_zones_need_cool(self, mock_hass, sample_config, sample_zone_configs):
        """Should activate cooling when zones need cooling and mode is cool."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "cool"
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.get_zones_needing_cooling = Mock(return_value=["living", "master_bed"])
        
        assert engine.should_activate_cooling(state_manager) is True
    
    def test_should_not_activate_cooling_when_no_zones_need_cool(self, mock_hass, sample_config, sample_zone_configs):
        """Should not activate cooling when no zones need cooling."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "cool"
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.get_zones_needing_cooling = Mock(return_value=[])
        
        assert engine.should_activate_cooling(state_manager) is False
    
    def test_should_not_activate_cooling_when_mode_is_heating(self, mock_hass, sample_config, sample_zone_configs):
        """Should not activate cooling when smart mode is heating."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "heat"
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.get_zones_needing_cooling = Mock(return_value=["living"])
        
        assert engine.should_activate_cooling(state_manager) is False


class TestIdleModeDecisions:
    """Test idle mode decision logic."""
    
    def test_should_switch_to_idle_heating_when_satisfied_and_dampers_low(self, mock_hass, sample_config, sample_zone_configs):
        """Should switch to DRY when heating satisfied and dampers low."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.all_zones_satisfied = Mock(return_value=True)
        state_manager.all_dampers_low = Mock(return_value=True)
        
        assert engine.should_switch_to_idle(state_manager, HVACMode.HEAT) is True
    
    def test_should_switch_to_idle_cooling_when_satisfied_and_dampers_low(self, mock_hass, sample_config, sample_zone_configs):
        """Should switch to FAN when cooling satisfied and dampers low."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.all_zones_satisfied = Mock(return_value=True)
        state_manager.all_dampers_low = Mock(return_value=True)
        
        assert engine.should_switch_to_idle(state_manager, HVACMode.COOL) is True
    
    def test_should_not_switch_to_idle_when_zones_not_satisfied(self, mock_hass, sample_config, sample_zone_configs):
        """Should not switch to idle when zones not satisfied."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.all_zones_satisfied = Mock(return_value=False)
        state_manager.all_dampers_low = Mock(return_value=True)
        
        assert engine.should_switch_to_idle(state_manager, HVACMode.HEAT) is False
    
    def test_should_not_switch_to_idle_when_dampers_not_low(self, mock_hass, sample_config, sample_zone_configs):
        """Should not switch to idle when dampers not low."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.all_zones_satisfied = Mock(return_value=True)
        state_manager.all_dampers_low = Mock(return_value=False)
        
        assert engine.should_switch_to_idle(state_manager, HVACMode.HEAT) is False


class TestTargetHVACModeLogic:
    """Test target HVAC mode determination."""
    
    def test_get_target_hvac_mode_heating_active(self, mock_hass, sample_config, sample_zone_configs):
        """Should return HEAT when heating should be active."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "heat"
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.get_zones_needing_heating = Mock(return_value=["living"])
        
        assert engine.get_target_hvac_mode(state_manager) == HVACMode.HEAT
    
    def test_get_target_hvac_mode_heating_idle(self, mock_hass, sample_config, sample_zone_configs):
        """Should return DRY when heating mode but no zones need heat."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "heat"
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.get_zones_needing_heating = Mock(return_value=[])
        
        assert engine.get_target_hvac_mode(state_manager) == HVACMode.DRY
    
    def test_get_target_hvac_mode_cooling_active(self, mock_hass, sample_config, sample_zone_configs):
        """Should return COOL when cooling should be active."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "cool"
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.get_zones_needing_cooling = Mock(return_value=["living"])
        
        assert engine.get_target_hvac_mode(state_manager) == HVACMode.COOL
    
    def test_get_target_hvac_mode_cooling_idle(self, mock_hass, sample_config, sample_zone_configs):
        """Should return FAN when cooling mode but no zones need cooling."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "cool"
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        state_manager.get_zones_needing_cooling = Mock(return_value=[])
        
        assert engine.get_target_hvac_mode(state_manager) == HVACMode.FAN
    
    def test_get_target_hvac_mode_uses_automatic_idle_logic(self, mock_hass, sample_config, sample_zone_configs):
        """Should use automatic idle mode logic based on smart_hvac_mode."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock no zones needing attention to trigger idle mode
        state_manager.get_zones_needing_heating = Mock(return_value=[])
        state_manager.get_zones_needing_cooling = Mock(return_value=[])
        
        # Test heating mode -> DRY idle
        config.smart_hvac_mode = "heat"
        assert engine.get_target_hvac_mode(state_manager) == HVACMode.DRY
        
        # Test cooling mode -> FAN idle  
        config.smart_hvac_mode = "cool"
        assert engine.get_target_hvac_mode(state_manager) == HVACMode.FAN
    
    def test_heat_to_dry_transition_multiple_active_zones(self, mock_hass, sample_config, sample_zone_configs):
        """Should transition HEAT → DRY when all multiple active non-isolated zones are satisfied."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "heat"
        config.temp_tolerance = 0.5
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        decision_engine = DecisionEngine(config)
        
        # Setup multiple active non-isolated zones
        living_zone = state_manager.zones["living"]
        living_zone.is_active = True
        living_zone.target_temp = 20.0
        living_zone.current_temp = 19.4  # Initially needs heating (< 20.0 - 0.5 = 19.5)
        
        master_zone = state_manager.zones["master_bed"]  
        master_zone.is_active = True
        master_zone.target_temp = 21.0
        master_zone.current_temp = 20.4  # Initially needs heating (< 21.0 - 0.5 = 20.5)
        
        baby_zone = state_manager.zones["baby_bed"]
        baby_zone.is_active = False  # Isolated zone inactive
        
        # Initially both zones need heating
        zones_needing_heat = state_manager.get_zones_needing_heating()
        assert "living" in zones_needing_heat
        assert "master_bed" in zones_needing_heat
        target_mode = decision_engine.get_target_hvac_mode(state_manager)
        assert target_mode == HVACMode.HEAT
        
        # Now both zones reach satisfaction (temp > target)
        living_zone.current_temp = 20.1  # > 20.0 target = satisfied
        master_zone.current_temp = 21.1  # > 21.0 target = satisfied
        
        # Should transition to DRY when all active zones satisfied
        zones_needing_heat = state_manager.get_zones_needing_heating()
        assert zones_needing_heat == []  # No zones need heating anymore
        assert state_manager.all_zones_satisfied(HVACMode.HEAT) == True
        target_mode = decision_engine.get_target_hvac_mode(state_manager)
        assert target_mode == HVACMode.DRY
    
    def test_cool_to_fan_transition_multiple_active_zones(self, mock_hass, sample_config, sample_zone_configs):
        """Should transition COOL → FAN when all multiple active non-isolated zones are satisfied."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "cool"
        config.temp_tolerance = 0.5
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        decision_engine = DecisionEngine(config)
        
        # Setup multiple active non-isolated zones
        living_zone = state_manager.zones["living"]
        living_zone.is_active = True
        living_zone.target_temp = 22.0
        living_zone.current_temp = 22.6  # Initially needs cooling (> 22.0 + 0.5 = 22.5)
        
        master_zone = state_manager.zones["master_bed"]  
        master_zone.is_active = True
        master_zone.target_temp = 23.0
        master_zone.current_temp = 23.6  # Initially needs cooling (> 23.0 + 0.5 = 23.5)
        
        baby_zone = state_manager.zones["baby_bed"]
        baby_zone.is_active = False  # Isolated zone inactive
        
        # Initially both zones need cooling
        zones_needing_cool = state_manager.get_zones_needing_cooling()
        assert "living" in zones_needing_cool
        assert "master_bed" in zones_needing_cool
        target_mode = decision_engine.get_target_hvac_mode(state_manager)
        assert target_mode == HVACMode.COOL
        
        # Now both zones reach satisfaction (temp < target)
        living_zone.current_temp = 21.9  # < 22.0 target = satisfied
        master_zone.current_temp = 22.9  # < 23.0 target = satisfied
        
        # Should transition to FAN when all active zones satisfied
        zones_needing_cool = state_manager.get_zones_needing_cooling()
        assert zones_needing_cool == []  # No zones need cooling anymore
        assert state_manager.all_zones_satisfied(HVACMode.COOL) == True
        target_mode = decision_engine.get_target_hvac_mode(state_manager)
        assert target_mode == HVACMode.FAN


class TestDamperCalculations:
    """Test damper position calculation logic."""
    
    def test_damper_calculation_inactive_zones_get_zero(self, mock_hass, sample_config, sample_zone_configs):
        """Inactive zones should get 0% damper."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Mock zone states
        mock_zones = {
            "living": Mock(is_active=True, isolation=False),
            "baby_bed": Mock(is_active=False, isolation=True),
        }
        state_manager.get_all_zone_states = Mock(return_value=mock_zones)
        
        positions = engine.calculate_damper_positions(state_manager, ["living"], HVACMode.HEAT)
        
        assert positions["baby_bed"] == 0
    
    def test_damper_calculation_trigger_zones_get_primary_percent(self, mock_hass, sample_config, sample_zone_configs):
        """Trigger zones should get primary damper percentage."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        mock_zones = {
            "living": Mock(is_active=True, isolation=False),
        }
        state_manager.get_all_zone_states = Mock(return_value=mock_zones)
        
        positions = engine.calculate_damper_positions(state_manager, ["living"], HVACMode.HEAT)
        
        assert positions["living"] == config.primary_damper_percent
    
    def test_damper_calculation_isolated_non_trigger_gets_minimum(self, mock_hass, sample_config, sample_zone_configs):
        """Isolated zones that didn't trigger should get minimum damper."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        mock_zones = {
            "living": Mock(is_active=True, isolation=False),
            "baby_bed": Mock(is_active=True, isolation=True),
        }
        state_manager.get_all_zone_states = Mock(return_value=mock_zones)
        
        positions = engine.calculate_damper_positions(state_manager, ["living"], HVACMode.HEAT)
        
        assert positions["baby_bed"] == config.minimum_damper_percent
    
    def test_damper_calculation_heating_secondary_zones(self, mock_hass, sample_config, sample_zone_configs):
        """Secondary zones in heating should get appropriate damper based on temperature."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Zone below target - should get secondary damper
        zone_below_target = Mock(
            is_active=True, 
            isolation=False,
            current_temp=19.0,
            target_temp=20.0
        )
        
        # Zone above target but below max - should get overflow damper
        zone_above_target = Mock(
            is_active=True,
            isolation=False, 
            current_temp=20.2,
            target_temp=20.0
        )
        
        mock_zones = {
            "living": Mock(is_active=True, isolation=False),  # trigger zone
            "master_bed": zone_below_target,
            "study": zone_above_target,
        }
        state_manager.get_all_zone_states = Mock(return_value=mock_zones)
        
        positions = engine.calculate_damper_positions(state_manager, ["living"], HVACMode.HEAT)
        
        assert positions["living"] == config.primary_damper_percent
        assert positions["master_bed"] == config.secondary_damper_percent
        assert positions["study"] == config.overflow_damper_percent
    
    def test_damper_calculation_cooling_secondary_zones(self, mock_hass, sample_config, sample_zone_configs):
        """Secondary zones in cooling should get appropriate damper based on temperature."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        # Zone above target - should get secondary damper
        zone_above_target = Mock(
            is_active=True,
            isolation=False,
            current_temp=25.0,
            target_temp=24.0
        )
        
        # Zone below target but above min - should get overflow damper
        zone_below_target = Mock(
            is_active=True,
            isolation=False,
            current_temp=23.8,
            target_temp=24.0
        )
        
        mock_zones = {
            "living": Mock(is_active=True, isolation=False),  # trigger zone
            "master_bed": zone_above_target,
            "study": zone_below_target,
        }
        state_manager.get_all_zone_states = Mock(return_value=mock_zones)
        
        positions = engine.calculate_damper_positions(state_manager, ["living"], HVACMode.COOL)
        
        assert positions["living"] == config.primary_damper_percent
        assert positions["master_bed"] == config.secondary_damper_percent
        assert positions["study"] == config.overflow_damper_percent


@pytest.mark.edge_case
class TestDecisionEngineEdgeCases:
    """Test edge cases for DecisionEngine."""
    
    def test_unknown_hvac_mode_returns_dry(self, mock_hass, sample_config, sample_zone_configs):
        """Unknown smart HVAC mode should default to DRY."""
        config = ControllerConfig(**sample_config)
        config.smart_hvac_mode = "unknown"
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, sample_zone_configs)
        
        assert engine.get_target_hvac_mode(state_manager) == HVACMode.DRY
    
    def test_no_zones_configured(self, mock_hass, sample_config):
        """Should handle case with no zones configured."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, {})
        state_manager.get_all_zone_states = Mock(return_value={})
        
        positions = engine.calculate_damper_positions(state_manager, [], HVACMode.HEAT)
        assert positions == {}
    
    def test_all_zones_isolated(self, mock_hass, sample_config):
        """Should handle case where all zones are isolated."""
        config = ControllerConfig(**sample_config)
        engine = DecisionEngine(config)
        
        state_manager = StateManager(mock_hass, config, {})
        
        mock_zones = {
            "zone1": Mock(is_active=True, isolation=True),
            "zone2": Mock(is_active=True, isolation=True),
        }
        state_manager.get_all_zone_states = Mock(return_value=mock_zones)
        
        positions = engine.calculate_damper_positions(state_manager, ["zone1"], HVACMode.HEAT)
        
        # Trigger zone should get primary, other isolated zone gets minimum
        assert positions["zone1"] == config.primary_damper_percent
        assert positions["zone2"] == config.minimum_damper_percent