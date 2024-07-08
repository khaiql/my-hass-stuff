import appdaemon.plugins.hass.hassapi as hass
from itertools import groupby
from operator import attrgetter
from appdaemon.exceptions import TimeOutException

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

    async def is_ac_controlled(self):
        return await self.zone_state.is_state('on')

    async def is_running(self):
        return await self.fingerbot_switch.is_state('on')

    async def get_current_temperature(self):
        return float(await self.temperature_sensor.get_state())

    async def get_desired_temperature(self, global_setting=None):
        if self.desired_temperature_setting_entity is not None:
            return float(await self.desired_temperature_setting_entity.get_state())
        return global_setting

    async def get_threshold(self, global_setting=None):
        if self.threshold_entity is not None:
            return float(await self.threshold_entity.get_state())
        return global_setting

    async def has_reached_desired_temp(self, global_desired_temperature, mode='heating'):
        current_temp = await self.get_current_temperature()
        desired_temperature = await self.get_desired_temperature(global_setting=global_desired_temperature)
        if mode == 'heating':
            return current_temp >= desired_temperature

        return current_temp <= desired_temperature # cooling mode

    async def is_out_of_desired_temp(self, global_desired_temperature, global_threshold, mode='heating'):
        current_temp = await self.get_current_temperature()
        desired_temperature = await self.get_desired_temperature(global_setting=global_desired_temperature)
        threshold = await self.get_threshold(global_setting=global_threshold)

        if mode == 'heating':
            return current_temp < desired_temperature - threshold

        return current_temp > desired_temperature - threshold

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
    async def initialize(self):
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

    async def get_desired_temperature(self):
        return float(await self.desired_temperature_entity.get_state())

    async def get_trigger_threshold(self):
        return float(await self.trigger_threshold_entity.get_state())

    async def get_mode(self):
        return await self.mode_entity.get_state()

    async def get_power_on_strategy(self):
        return await self.power_on_strategy_entity.get_state()

    async def active_zones(self, sort=False):
        zones = [z for z in self.zones if await z.is_ac_controlled()]
        if sort:
            zones.sort(key=lambda zone: zone.priority)
        return zones

    async def zone_groups(self):
        sorted_zones = await self.active_zones(sort=True)
        grouped_zones = groupby(sorted_zones, key=attrgetter('priority'))
        return [list(group) for _, group in grouped_zones]

    def find_trigger_zone(self, entity):
        return next((zone for zone in self.zones if zone.has_entity(entity)), None)

    async def smart_control(self, entity, attribute, old, new, pin_app, **kwargs):
        self.log(f"smart_control callback {entity=} {old=} {new=}")
        new_state = await self.determine_power_state()
        self.log(f"power {new_state=}")
        trigger_zone = None
        if new_state != await self.power_switch.get_state():
            await self.power_switch.toggle()
            trigger_zone = self.find_trigger_zone(entity) if new_state == 'on' else None

        if new_state == 'off':
            return

        zone_states = await self.determine_zone_switch_states(trigger_zone)
        self.log(f"zones {zone_states=}")

        # address an edge case where power remains on but all switches are expected to be off, due to delayed update from sensors
        if set(zone_states.values()) == set(['off']):
            await self.power_switch.toggle()
            return

        if zone_states:
            await self.switches_manager.update_states(**zone_states)


    async def determine_power_state(self):
        active_zones = await self.active_zones()

        if not active_zones:
            self.log("no active zones")
            return 'off'

        desired_temp = await self.get_desired_temperature()
        mode = await self.get_mode()
        trigger_threshold = await self.get_trigger_threshold()

        if await self.power_switch.get_state() == 'on':
            return 'off' if all([await zone.has_reached_desired_temp(desired_temp, mode=mode) for zone in active_zones]) else 'on'

        # Power switch is off
        out_of_desired_states = [await zone.is_out_of_desired_temp(desired_temp, trigger_threshold, mode=mode) for zone in active_zones]
        power_on_strategy = await self.get_power_on_strategy()

        if (power_on_strategy == 'all' and all(out_of_desired_states)) or \
        (power_on_strategy == 'any' and any(out_of_desired_states)):
            return 'on'

        return 'off'

    async def determine_zone_switch_states(self, trigger_zone: Zone = None):
        active_zones = await self.active_zones()
        states = {zone.name: 'off' for zone in active_zones}

        if trigger_zone:
            states[trigger_zone.name] = 'on'
            return states

        desired_temp = await self.get_desired_temperature()
        mode = await self.get_mode()
        trigger_threshold = await self.get_trigger_threshold()

        zone_groups = await self.zone_groups()

        for index, group in enumerate(zone_groups):
            group_active = False
            for zone in group:
                if await zone.is_running():
                    states[zone.name] = 'off' if await zone.has_reached_desired_temp(desired_temp, mode=mode) else 'on'
                else:
                    states[zone.name] = 'on' if await zone.is_out_of_desired_temp(desired_temp, trigger_threshold, mode=mode) else 'off'

                group_active = group_active or states[zone.name] == 'on'

            if group_active:
                for lower_group in zone_groups[index + 1:]:
                    for zone in lower_group:
                        states[zone.name] = 'off'
                break

        return states


class SwitchesManager:
    def __init__(self, adapi, bedroom_switch=None, kitchen_switch=None, study_switch=None):
        self.adapi = adapi
        self.bedroom_switch = bedroom_switch
        self.kitchen_switch = kitchen_switch
        self.study_switch = study_switch

    async def update_states(self, bedroom=None, kitchen=None, study=None, ensure_state=True):
        try:
            if kitchen != None and not await self.kitchen_switch.is_state(kitchen):
                await self.kitchen_switch.toggle()
                await self.kitchen_switch.wait_state(kitchen, timeout=10)

            if study != None and not await self.study_switch.is_state(study):
                await self.study_switch.toggle()
                await self.study_switch.wait_state(study, timeout=10)

            if bedroom is not None and not await self.bedroom_switch.is_state(bedroom):
                await self.bedroom_switch.toggle()
                await self.bedroom_switch.wait_state(bedroom, timeout=10)

        except TimeOutException:
            pass # didn't complete on time
