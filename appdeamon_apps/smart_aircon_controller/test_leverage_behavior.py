#!/usr/bin/env python3
"""
Test to demonstrate leverage heat behavior clearly
"""

from test_automation_logic import MockSmartAirconController, ControllerConfig, ZoneState, HVACMode


def test_leverage_heat_behavior():
    """Test the specific leverage heat behavior"""
    print("LEVERAGE HEAT BEHAVIOR DEMONSTRATION")
    print("=" * 60)
    
    config = ControllerConfig(
        smart_hvac_mode="heat",
        temp_tolerance=0.5,
        primary_damper_percent=50,
        secondary_damper_percent=40,
        overflow_damper_percent=10
    )
    controller = MockSmartAirconController(config)
    
    # Clear scenario: one zone triggers, others leverage heat
    controller.zones = {
        "trigger_zone": ZoneState(
            entity_id="climate.trigger",
            damper_entity="cover.trigger_damper",
            current_temp=19.2,  # Below target - tolerance, triggers heating
            target_temp=20.0,
            is_active=True,
            isolation=False
        ),
        "leverage_zone_1": ZoneState(
            entity_id="climate.leverage1",
            damper_entity="cover.leverage1_damper", 
            current_temp=20.2,  # Above target but below target + tolerance
            target_temp=20.0,   # Should heat to 20.5°C to leverage energy
            is_active=True,
            isolation=False
        ),
        "leverage_zone_2": ZoneState(
            entity_id="climate.leverage2",
            damper_entity="cover.leverage2_damper",
            current_temp=18.8,  # Below target, should heat normally
            target_temp=19.0,
            is_active=True,
            isolation=False
        ),
        "no_leverage_zone": ZoneState(
            entity_id="climate.no_leverage",
            damper_entity="cover.no_leverage_damper",
            current_temp=19.6,  # Already at target + tolerance
            target_temp=19.0,   # Should NOT heat further
            is_active=True,
            isolation=False
        )
    }
    
    print("SETUP:")
    print("- Trigger zone: 19.2°C (needs heating), target 20.0°C")
    print("- Leverage zone 1: 20.2°C (above target), target 20.0°C → should heat to 20.5°C")
    print("- Leverage zone 2: 18.8°C (below target), target 19.0°C → should heat normally") 
    print("- No leverage zone: 19.6°C (at max), target 19.0°C → should NOT heat")
    print()
    
    # Run the algorithm
    print("RUNNING ALGORITHM...")
    controller.periodic_check()
    
    print("\nDAMPER POSITIONS:")
    for zone_name, zone in controller.zones.items():
        max_desired = zone.target_temp + config.temp_tolerance
        should_heat = zone.current_temp < max_desired
        print(f"{zone_name:16}: {zone.damper_position:2d}% | Current: {zone.current_temp:4.1f}°C | Target: {zone.target_temp:4.1f}°C | Max: {max_desired:4.1f}°C | Should heat: {should_heat}")
    
    print(f"\nHVAC Mode: {controller.current_hvac_mode}")
    print(f"Algorithm Active: {controller.algorithm_active}")
    
    print("\nEXPECTED BEHAVIOR:")
    print("✓ Trigger zone: 50% (primary trigger)")
    print("✓ Leverage zone 1: 10% (leverage heat to 20.5°C)")
    print("✓ Leverage zone 2: 40% (below target, normal heating)")
    print("✓ No leverage zone: 0% (already at max desired temp)")


if __name__ == "__main__":
    test_leverage_heat_behavior()