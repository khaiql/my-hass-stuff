import appdaemon.plugins.hass.hassapi as hass
from itertools import groupby
from operator import attrgetter

SETTING_DELAY_DURATION_SECOND=2

class Zone:
    def __init__(self, adapi, name, config={}):
        self.adapi = adapi
        self.name = name

        self.priority = int(config["priority"])
        self.temperature_sensor = self.adapi.get_entity(config["temperature_entity_id"])
        self.fingerbot_switch = self.adapi.get_entity(config["switch_entity_id"])
        self.zone_state = self.adapi.get_entity(config["state_entity_id"])

        self.desired_temperature_setting_entity = self.adapi.get_entity(config["desired_temperature_entity_id"]) if "desired_temperature_entity_id" in config else None
        self.threshold_entity = self.adapi.get_entity(config["threshold_entity_id"]) if "threshold_entity_id" in config else None

    def is_ac_controlled(self):
        return self.zone_state.get_state() == 'on'

    def is_running(self):
        return self.fingerbot_switch.is_state('on')

    def get_current_temperature(self):
        return float(self.temperature_sensor.get_state())

    def get_desired_temperature(self, global_setting=None):
        if self.desired_temperature_setting_entity is not None:
            return float(self.desired_temperature_setting_entity.get_state())
        return global_setting

    def get_threshold(self, global_setting=None):
        if self.threshold_entity is not None:
            return float(self.threshold_entity.get_state())
        return global_setting

    def has_reached_desired_temp(self, global_desired_temperature, mode='heating'):
        current_temp = self.get_current_temperature()
        if mode == 'heating':
            return current_temp >= self.get_desired_temperature(global_setting=global_desired_temperature)

        return current_temp <= self.get_desired_temperature() # cooling mode

    def is_out_of_desired_temp(self, global_desired_temperature, global_threshold, mode='heating'):
        current_temp = self.get_current_temperature()
        if mode == 'heating':
            return current_temp < self.get_desired_temperature(global_setting=global_desired_temperature) - self.get_threshold(global_setting=global_threshold)

        return current_temp > self.get_desired_temperature(global_setting=global_desired_temperature) - self.get_threshold(global_setting=global_threshold)

    def has_entity(self, entity_id):
        return self.temperature_sensor.entity_id == entity_id or self.zone_state.entity_id == entity_id

    def listen_state(self, callback):
        self.temperature_sensor.listen_state(callback)
        self.zone_state.listen_state(callback)
        if self.desired_temperature_setting_entity is not None:
            self.desired_temperature_setting_entity.listen_state(callback, duration=SETTING_DELAY_DURATION_SECOND)
        if self.threshold_entity is not None:
            self.threshold_entity.listen_state(callback, duration=SETTING_DELAY_DURATION_SECOND)

    def __str__(self):
        return f"{self.name} priority={self.priority} active={self.is_ac_controlled()} switch_state={self.fingerbot_switch.get_state()} current_temp={self.get_current_temperature()}"

class AirconController(hass.Hass):
    def initialize(self):
        self.desired_temperature_entity = self.get_entity(self.args["desired_temperature_helper_id"])
        self.trigger_threshold_entity = self.get_entity(self.args["trigger_threshold_helper_id"])
        self.power_switch = self.get_entity(self.args["power_switch_entity_id"])
        self.mode_entity = self.get_entity(self.args["ac_mode_entity_id"])
        self.power_on_strategy_entity = self.get_entity(self.args["power_on_strategy_entity_id"])

        self.bedroom_zone = Zone(self.get_ad_api(), 'bedroom', config=self.args["bedroom"])
        self.kitchen_zone = Zone(self.get_ad_api(), 'kitchen', config=self.args["kitchen"])
        self.study_zone = Zone(self.get_ad_api(), 'study', config=self.args["study"])

        self.zones = [self.bedroom_zone, self.kitchen_zone, self.study_zone]

        self.switches_manager = SwitchesManager(self.get_ad_api(),
                                                bedroom_switch=self.bedroom_zone.fingerbot_switch,
                                                kitchen_switch=self.kitchen_zone.fingerbot_switch,
                                                study_switch=self.study_zone.fingerbot_switch,
                                                )

        # register state change callback
        for zone in self.zones:
            zone.listen_state(self.smart_control)

        self.desired_temperature_entity.listen_state(self.smart_control, duration=SETTING_DELAY_DURATION_SECOND)
        self.trigger_threshold_entity.listen_state(self.smart_control, duration=SETTING_DELAY_DURATION_SECOND)

    def get_desired_temperature(self):
        return float(self.desired_temperature_entity.get_state())

    def get_trigger_threshold(self):
        return float(self.trigger_threshold_entity.get_state())

    def get_mode(self):
        return self.mode_entity.get_state()

    def get_power_on_strategy(self):
        return self.power_on_strategy_entity.get_state()

    def active_zones(self, sort=False):
        zones = list(filter(lambda z: z.is_ac_controlled(), self.zones))
        if sort:
            zones.sort(key=lambda zone: zone.priority)
        return zones

    def zone_groups(self):
        sorted_zones = self.active_zones(sort=True)
        grouped_zones = groupby(sorted_zones, key=attrgetter('priority'))
        return [list(group) for _, group in grouped_zones]

    def find_trigger_zone(self, entity):
        return next((zone for zone in self.zones if zone.has_entity(entity)), None)

    def smart_control(self, entity, attribute, old, new, **kwargs):
        self.log(f"smart_control callback {entity=} {old=} {new=}")
        new_state = self.determine_power_state()
        self.log(f"power {new_state=}")
        trigger_zone = None
        if new_state != self.power_switch.get_state():
            self.power_switch.toggle()
            trigger_zone = self.find_trigger_zone(entity) if new_state == 'on' else None

        if new_state == 'off':
            return

        zone_states = self.determine_zone_switch_states(trigger_zone)
        self.log(f"zones {zone_states=}")

        # address an edge case where power remains on but all switches are expected to be off, due to delayed update from sensors
        if set(zone_states.values()) == set(['off']):
            self.power_switch.toggle()
            return

        if zone_states:
            self.switches_manager.update_states(**zone_states)


    def determine_power_state(self):
        if len(self.active_zones()) == 0:
            self.log("no active zones")
            return 'off'

        if self.power_switch.get_state() == 'on':
            # determine if it should be turned off
            desired_states = map(lambda z: z.has_reached_desired_temp(self.get_desired_temperature(), mode=self.get_mode()),
                                self.active_zones())
            return 'off' if all(desired_states) else 'on'
        elif self.power_switch.get_state() == 'off':
            out_of_desired_states = map(lambda z: z.is_out_of_desired_temp(
                self.get_desired_temperature(),
                self.get_trigger_threshold(),
                mode=self.get_mode()),
            self.active_zones())

            if self.get_power_on_strategy() == 'all' and all(out_of_desired_states):
                return 'on'
            if self.get_power_on_strategy() == 'at_least_one' and any(out_of_desired_states):
                return 'on'
            return 'off'

    def determine_zone_switch_states(self, trigger_zone: Zone=None):
        # we only want to manage switch of zones that are active
        states = {zone.name: 'off' for zone in self.active_zones()}

        # if the a/c is triggered to turn on by a zone, prioritize running that zone
        if trigger_zone is not None:
            states[trigger_zone.name] = 'on'
            return states

        groups = self.zone_groups()
        for index, group in enumerate(groups):
            # scenario 1: priority zone is running and has not reached desired temp, then keep it running and turn off other zones
            # scenario 2: priority zone is not running, but still within range, then keep it shut off and run other zones
            # scenario 3: priority zone is not running, and it's out of range, then turn it on
            group_state = None
            for zone in group:
                if zone.is_running():
                    if zone.has_reached_desired_temp(self.get_desired_temperature(), mode=self.get_mode()):
                        states[zone.name] = 'off'
                    else:
                        states[zone.name] = 'on'
                else:
                    if zone.is_out_of_desired_temp(self.get_desired_temperature(), self.get_trigger_threshold(), mode=self.get_mode()):
                        states[zone.name] = 'on' # turn the zone back on
                    else:
                        states[zone.name] = 'off' # keep it off and let other zones run

                group_state = 'on' if states[zone.name] == 'on' and group_state is None else None

            if group_state == 'on' and index < len(groups) - 1:
                lower_prio_zones = [zone for group in groups[index+1:] for zone in group]
                for zone in lower_prio_zones:
                    states[zone.name] = 'off'
                break

        return states


class SwitchesManager:
    def __init__(self, adapi, bedroom_switch=None, kitchen_switch=None, study_switch=None):
        self.adapi = adapi
        self.bedroom_switch = bedroom_switch
        self.kitchen_switch = kitchen_switch
        self.study_switch = study_switch


    def update_states(self, bedroom=None, kitchen=None, study=None):
        if kitchen != None and not self.kitchen_switch.is_state(kitchen):
            self.kitchen_switch.toggle()

        if study != None and not self.study_switch.is_state(study):
            self.study_switch.toggle()

        if self.study_switch.is_state('off') and self.kitchen_switch.is_state('off'):
            return # do nothing with bedroom because it's on anyway

        if bedroom is not None and not self.bedroom_switch.is_state(bedroom):
            self.bedroom_switch.toggle()
