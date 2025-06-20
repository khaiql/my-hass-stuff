# Smart Aircon Controller Testing Guide

This guide explains how to test the smart aircon controller safely using dry run mode and sensor simulation.

## 🔥 Dry Run Mode

Dry run mode allows you to test the controller logic without actually changing any devices. When enabled, the controller will:

- Log all actions it would take instead of executing them
- Show detailed decision-making process
- Display calculated damper positions
- Indicate HVAC mode changes

### Enabling Dry Run Mode

Dry run mode is now configured as a static parameter in your AppDaemon `apps.yaml` file:

```yaml
# apps.yaml - AppDaemon configuration
smart_aircon_controller:
  module: smart_aircon_controller
  class: SmartAirconController
  
  # Static configuration (requires restart to change)
  dry_run: true  # Enable dry run mode for safe testing
  check_interval: 30
  main_climate: "climate.aircon"
  # ... other static config
  
  # Zone configuration
  zones:
    lounge:
      climate_entity: "climate.lounge"
      damper_entity: "cover.lounge_damper"
    # ... other zones
  
  # Dynamic configuration entities (no dry_run here anymore)
  config_entities:
    enabled: "input_boolean.smart_aircon_enabled"
    smart_hvac_mode: "input_select.smart_aircon_hvac_mode"
    # ... other dynamic config
  
  # Fallback values
  config_defaults:
    enabled: false
    # ... other defaults (no dry_run here)
```

**Note:** Dry run mode requires an AppDaemon restart to change, making it safer for production deployments.

### Dry Run Log Examples

When dry run is enabled, you'll see logs like:

```
🔥 === DRY RUN MODE: PERIODIC CHECK START ===
Controller enabled: True, Smart HVAC mode: heat, Dry run: True
🔥 DRY RUN: Would set HVAC mode to heat
🔥 DRY RUN: Would restore zone target temperatures:
  - lounge: Would set to 21.0°C (entity: climate.lounge)
  - bedroom: Would set to 20.0°C (entity: climate.bedroom)
🔥 DRY RUN: Would set damper positions:
  - lounge: 50% (entity: cover.lounge_damper)
  - bedroom: 40% (entity: cover.bedroom_damper)
  - study: 5% (entity: cover.study_damper)
```

## 🎯 Sensor Simulation

Use the `sensor_simulator.py` script to create different test scenarios without affecting real sensors.

### Installation

```bash
pip install requests
```

### Quick Start

1. **List available scenarios:**
   ```bash
   python sensor_simulator.py --list
   ```

2. **Run a predefined scenario:**
   ```bash
   python sensor_simulator.py --scenario heating_needed --token YOUR_HA_TOKEN
   ```

3. **Create custom scenarios interactively:**
   ```bash
   python sensor_simulator.py --custom --token YOUR_HA_TOKEN
   ```

### Getting a Home Assistant Token

1. Go to your Home Assistant profile (click your user icon)
2. Scroll to "Long-Lived Access Tokens"
3. Click "Create Token"
4. Copy the token and use it with the simulator

### Available Test Scenarios

#### 1. `heating_needed`
- **Purpose:** Test heating activation
- **Conditions:** Multiple zones below target temperature
- **Expected:** Controller should activate HEAT mode and set appropriate damper positions

#### 2. `cooling_needed`
- **Purpose:** Test cooling activation  
- **Conditions:** Multiple zones above target temperature in cooling mode
- **Expected:** Controller should activate COOL mode

#### 3. `satisfied_zones`
- **Purpose:** Test idle mode switching
- **Conditions:** All zones at target temperature
- **Expected:** Controller should switch to idle mode (DRY/FAN)

#### 4. `mixed_zones`
- **Purpose:** Test complex scenarios
- **Conditions:** Some zones satisfied, others need attention
- **Expected:** Selective damper control

#### 5. `controller_disabled`
- **Purpose:** Test disabled state
- **Conditions:** Controller disabled with zones needing attention
- **Expected:** No actions taken

## 🧪 Testing Workflow

### 1. Safe Testing Setup

1. **Enable dry run mode in apps.yaml:**
   ```yaml
   # apps.yaml - Set dry_run to true
   smart_aircon_controller:
     dry_run: true
     # ... rest of configuration
   ```

2. **Restart AppDaemon:**
   ```bash
   # Restart AppDaemon to apply the dry_run setting
   docker restart appdaemon  # or however you restart AppDaemon
   ```

3. **Monitor AppDaemon logs:**
   ```bash
   tail -f /config/appdaemon/logs/appdaemon.log
   ```

### 2. Progressive Testing

**Step 1: Verify Dry Run**
```bash
# Test with dry run enabled
python sensor_simulator.py --scenario heating_needed --token YOUR_TOKEN
```
Check logs - should see "🔥 DRY RUN" messages

**Step 2: Real Device Testing**
```bash
# Disable dry run in apps.yaml, restart AppDaemon, then test with simple scenario
# Set dry_run: false in apps.yaml, then restart AppDaemon
docker restart appdaemon
python sensor_simulator.py --scenario satisfied_zones --token YOUR_TOKEN
```

**Step 3: Complex Scenarios**
Test more complex scenarios once basic functionality is verified.

### 3. Manual Testing via Home Assistant UI

You can also test manually using the Developer Tools:

1. **Go to Developer Tools → States**
2. **Set entity states manually:**

   ```yaml
   # Example: Simulate heating needed
   climate.lounge:
     state: "heat"
     attributes:
       temperature: 21.0
       current_temperature: 18.5
       hvac_mode: "heat"

   cover.lounge_damper:
     state: "open"  
     attributes:
       current_position: 5
   ```

## 🔍 Understanding Controller Behavior

### Decision Logic Flow

1. **Check if controller enabled**
   - If disabled: No actions taken

2. **Update all zone states**
   - Read temperatures, damper positions
   - Check which zones are active

3. **Determine target HVAC mode**
   - HEAT: If zones need heating
   - COOL: If zones need cooling  
   - IDLE (DRY/FAN): If zones satisfied

4. **Algorithm activation logic**
   - Activate if target mode requires heating/cooling
   - Deactivate if all zones satisfied
   - Consider stability time gaps

5. **Damper calculation**
   - Primary zones: 50% (configurable)
   - Secondary zones: 40% (configurable)
   - Overflow zones: 10% (configurable)
   - Minimum active: 5% (configurable)

### Key Configuration Parameters

```yaml
# Timing controls
stability_check_minutes: 10  # Min time between HVAC changes
algorithm_timeout_minutes: 30  # Max algorithm runtime
progress_timeout_minutes: 15  # Max time without progress

# Damper controls  
primary_damper_percent: 50    # Primary triggering zones
secondary_damper_percent: 40  # Secondary zones needing service
overflow_damper_percent: 10   # Zones above target but not satisfied
minimum_damper_percent: 5     # Minimum for active zones

# Temperature control
temp_tolerance: 0.5  # Temperature tolerance (°C)
```

## 🚨 Troubleshooting

### Common Issues

1. **"Entity not found" errors**
   - Update `ZONE_CONFIGS` in `sensor_simulator.py` to match your entities
   - Verify entity names in Home Assistant

2. **No dry run logs appearing**
   - Check that `dry_run: true` is set in your `apps.yaml` file
   - Verify AppDaemon has been restarted after changing the dry_run setting
   - Check for errors in AppDaemon logs during startup

3. **Controller not reacting to simulated changes**
   - Check that controller is enabled
   - Verify AppDaemon is running and loading the app
   - Check for errors in AppDaemon logs

4. **Simulator connection issues**
   - Verify Home Assistant URL is correct
   - Check that token has proper permissions
   - Ensure Home Assistant API is accessible

### Debug Commands

```bash
# Check AppDaemon logs
tail -f /config/appdaemon/logs/appdaemon.log | grep -i "smart.*aircon"

# Check specific entity states
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://homeassistant.local:8123/api/states/climate.lounge

# List all entities matching pattern
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://homeassistant.local:8123/api/states | grep -i climate
```

## 📊 Advanced Testing

### Stress Testing
Create scenarios with rapid temperature changes to test stability controls:

```bash
# Quick succession testing
python sensor_simulator.py --scenario heating_needed --token YOUR_TOKEN
sleep 30
python sensor_simulator.py --scenario satisfied_zones --token YOUR_TOKEN  
sleep 30
python sensor_simulator.py --scenario cooling_needed --token YOUR_TOKEN
```

### Performance Testing
Monitor resource usage during algorithm execution:

```bash
# Monitor AppDaemon process
top -p $(pgrep -f appdaemon)

# Check memory usage
ps aux | grep appdaemon
```

### Edge Case Testing
Test boundary conditions:
- Exactly at temperature tolerance boundaries
- All zones inactive
- Mix of isolated and normal zones
- Configuration value changes during operation

## 🎯 Best Practices

1. **Always start with dry run enabled**
2. **Test one scenario at a time**
3. **Monitor logs continuously during testing**
4. **Keep a log of what scenarios work/fail**
5. **Test configuration changes separately**
6. **Use version control for configuration changes**
7. **Document any custom scenarios you create**

This testing framework allows you to thoroughly validate the controller behavior before deploying to your actual HVAC system. 