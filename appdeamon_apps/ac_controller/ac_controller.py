from datetime import datetime
from itertools import groupby
from operator import attrgetter
from typing import Optional

import appdaemon.plugins.hass.hassapi as hass
from appdaemon.exceptions import TimeOutException

from ac_zone import SETTING_DELAY_DURATION_SECOND, Zone


def is_increasing(arr):
    if len(arr) > 0:
        return all(x < y for x, y in zip(arr, arr[1:]))
    return False


def is_decreasing(arr):
    if len(arr) > 0:
        return all(x > y for x, y in zip(arr, arr[1:]))
    return False


def flatten(nested_list):
    return [item for sublist in nested_list for item in sublist]


class AirconController(hass.Hass):
    async def initialize(self):
        self.desired_temperature_entity = self.get_entity(
            self.args["desired_temperature_helper_id"]
        )
        self.trigger_threshold_entity = self.get_entity(
            self.args["trigger_threshold_helper_id"]
        )
        self.power_switch = self.get_entity(self.args["power_switch_entity_id"])
        self.mode_entity = self.get_entity(self.args["ac_mode_entity_id"])
        self.power_on_strategy_entity = self.get_entity(
            self.args["power_on_strategy_entity_id"]
        )
        self.self_fix_toggle = self.get_entity(self.args["self_fix_toggle_entity_id"])

        self.bedroom_zone = Zone(
            self.get_ad_api(), "bedroom", config=self.args["bedroom"]
        )
        self.baby_bedroom_zone = Zone(
            self.get_ad_api(), "bedroom", config=self.args["baby_bedroom"]
        )
        self.kitchen_zone = Zone(
            self.get_ad_api(), "kitchen", config=self.args["kitchen"]
        )
        self.study_zone = Zone(self.get_ad_api(), "study", config=self.args["study"])

        self.zones = [self.bedroom_zone, self.baby_bedroom_zone, self.kitchen_zone, self.study_zone]

        self.switches_manager = SwitchesManager(
            self.get_ad_api(),
            bedroom_zone=self.bedroom_zone,
            baby_bedroom_zone=self.baby_bedroom_zone,
            kitchen_zone=self.kitchen_zone,
            study_zone=self.study_zone,
        )

        # register state change callback
        for zone in self.zones:
            zone.listen_state(self.smart_control)

        self.desired_temperature_entity.listen_state(
            self.smart_control, duration=SETTING_DELAY_DURATION_SECOND
        )
        self.trigger_threshold_entity.listen_state(
            self.smart_control, duration=SETTING_DELAY_DURATION_SECOND
        )

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
        grouped_zones = groupby(sorted_zones, key=attrgetter("priority"))
        return [list(group) for _, group in grouped_zones]

    def find_trigger_zone(self, entity) -> Optional[Zone]:
        zone = next((zone for zone in self.zones if zone.has_entity(entity)), None)
        if zone:
            self.log(f"debug trigger_zone={zone.name}")
        return zone

    async def toggle_power_switch(self, expected_state: str):
        await self.power_switch.toggle()
        await self.sleep(3)

    async def should_double_check_power_state(self, entity: str):
        if self.self_fix_toggle.state != 'on':
            return False

        active_zones = await self.active_zones()
        if len(active_zones) > 1:
            return False
        entities = [zone.temperature_sensor.entity_id for zone in active_zones]
        self.log(f"{entities=}")
        return entity in entities

    async def smart_control(self, *args, **kwargs):
        entity, old, new = args[0], args[2], args[3]
        self.log(f"smart_control callback {entity=} {old=} {new=}")

        if await self.should_double_check_power_state(
            entity
        ) and await self.ensure_power_state_correct(entity, new):
            self.log("fixed incorrect power state, skip other checks")
            return

        trigger_zone = self.find_trigger_zone(entity)
        if trigger_zone and not await trigger_zone.is_ac_controlled():
            return

        new_state = await self.determine_power_state()
        self.log(f"power {new_state=}")

        if new_state != self.power_switch.state:
            await self.toggle_power_switch(new_state)
        else:
            trigger_zone = None

        if new_state == "off":
            return

        zone_states = await self.determine_zone_switch_states(trigger_zone)
        self.log(f"zones {zone_states=}")

        # address an edge case where power remains on but all switches are expected to be off, due to delayed update from sensors
        if set(zone_states.values()) == set(["off"]):
            await self.toggle_power_switch("off")
            return

        if zone_states:
            await self.switches_manager.update_states(**zone_states)

    async def ensure_power_state_correct(
        self, temperature_sensor_entity: str, new_value: str
    ) -> bool:
        if new_value.lower() == "unavailable":
            return False

        power_history = flatten(
            await self.get_history(entity_id=self.power_switch.entity_id, days=1)
        )
        last_power_history = power_history[-1]
        last_power_history_changed = datetime.fromisoformat(
            last_power_history["last_changed"]
        )

        temp_sensor_history = flatten(
            await self.get_history(entity_id=temperature_sensor_entity, days=1)
        )

        temperatures_order_by_time_desc = [float(new_value)]
        for entry in temp_sensor_history[::-1]:
            last_changed = datetime.fromisoformat(entry["last_changed"])
            if last_changed < last_power_history_changed:
                break
            if entry["state"].lower() != "unavailable":
                temperatures_order_by_time_desc.append(float(entry["state"]))

        if len(temperatures_order_by_time_desc) < 4:  # need at least 4 data points
            return False

        temperatures_order_by_time_asc = temperatures_order_by_time_desc[:4][::-1]

        self.log(f"temperature history of {temperature_sensor_entity} {temperatures_order_by_time_desc=} {temperatures_order_by_time_asc=}")

        if await self.is_power_in_wrong_state(temperatures_order_by_time_asc):
            await self.revert_power_state_to_fix_mqtt_issue()
            return True
        return False

    async def is_power_in_wrong_state(self, temperatures_order_by_time_asc):
        mode = await self.get_mode()
        current_power_state = await self.power_switch.get_state()
        is_wrong = False
        if (
            mode == "heating"
            and current_power_state == "on"
            and is_decreasing(temperatures_order_by_time_asc)
        ):
            is_wrong = True
            self.log("detecting power is on but temperature keeps decreasing")
        elif (
            mode == "heating"
            and current_power_state == "off"
            and is_increasing(temperatures_order_by_time_asc)
        ):
            is_wrong = True
            self.log("detecting power is off but temperature keeps increasing")
        elif (
            mode == "cooling"
            and current_power_state == "on"
            and is_increasing(temperatures_order_by_time_asc)
        ):
            is_wrong = True
            self.log("detecting power is on but temperature keeps increasing")
        elif (
            mode == "cooling"
            and current_power_state == "off"
            and is_decreasing(temperatures_order_by_time_asc)
        ):
            is_wrong = True
            self.log("detecting power is off but temperature keeps decreasing")

        return is_wrong

    async def revert_power_state_to_fix_mqtt_issue(self):
        # power switch is in the right state, however it is doubled clicked due to MQTT hiccups, so set the state to
        # current state but publishing the message to toggle the A/C
        current_state = await self.power_switch.get_state()
        payload = f'{{"state": "{current_state}"}}'
        self.log(f"setting {payload=}")
        topic = f"zigbee2mqtt/{self.power_switch.friendly_name}/set"
        await self.call_service("mqtt/publish", topic=topic, payload=payload)

    async def determine_power_state(self):
        active_zones = await self.active_zones()

        if not active_zones:
            self.log("no active zones")
            return "off"

        active_zone_names = [zone.name for zone in active_zones]
        self.log(f"determine_power_state {active_zone_names=}")

        desired_temp = await self.get_desired_temperature()
        mode = await self.get_mode()
        trigger_threshold = await self.get_trigger_threshold()

        if await self.power_switch.is_state("on"):
            return (
                "off"
                if all(
                    [
                        await zone.has_reached_desired_temp(global_desired_temperature=desired_temp, mode=mode)
                        for zone in active_zones
                    ]
                )
                else "on"
            )

        # Power switch is off
        out_of_desired_states = [
            await zone.is_out_of_desired_temp(
                global_desired_temperature=desired_temp, global_threshold=trigger_threshold, mode=mode
            )
            for zone in active_zones
        ]
        power_on_strategy = await self.get_power_on_strategy()
        self.log(f"determine_power_state {out_of_desired_states=} {power_on_strategy=}")

        if (power_on_strategy == "all" and all(out_of_desired_states)) or (
            power_on_strategy == "any" and any(out_of_desired_states)
        ):
            return "on"

        return "off"

    async def determine_zone_switch_states(self, trigger_zone: Optional[Zone] = None):
        active_zones = await self.active_zones()
        states = {zone.name: "off" for zone in active_zones}

        if trigger_zone:
            states[trigger_zone.name] = "on"
            return states

        desired_temp = await self.get_desired_temperature()
        mode = await self.get_mode()
        trigger_threshold = await self.get_trigger_threshold()

        zone_groups = await self.zone_groups()

        for index, group in enumerate(zone_groups):
            group_active = False
            for zone in group:
                if await zone.is_running():
                    states[zone.name] = (
                        "off"
                        if await zone.has_reached_desired_temp(desired_temp, mode=mode)
                        else "on"
                    )
                else:
                    states[zone.name] = (
                        "on"
                        if await zone.is_out_of_desired_temp(
                            desired_temp, trigger_threshold, mode=mode
                        )
                        else "off"
                    )

                group_active = group_active or states[zone.name] == "on"

            if group_active:
                for lower_group in zone_groups[index + 1 :]:
                    for zone in lower_group:
                        states[zone.name] = "off"
                break

        return states


class SwitchesManager:
    def __init__(self, adapi, bedroom_zone: Zone, baby_bedroom_zone: Zone, kitchen_zone: Zone, study_zone: Zone):
        self.adapi = adapi
        self.bedroom_zone = bedroom_zone
        self.baby_bedroom_zone = baby_bedroom_zone
        self.kitchen_zone = kitchen_zone
        self.study_zone = study_zone

    async def update_states(self, bedroom=None, kitchen=None, study=None):
        try:
            if kitchen and not await self.kitchen_zone.is_switch_state(kitchen):
                await self.kitchen_zone.toggle_switch_and_wait_state(kitchen)

            if study and not await self.study_zone.is_switch_state(study):
                await self.study_zone.toggle_switch_and_wait_state(study)

            if bedroom and (not await self.bedroom_zone.is_switch_state(bedroom) or not await
                            self.baby_bedroom_zone.is_switch_state(bedroom)):
                await self.bedroom_zone.toggle_switch_and_wait_state(bedroom) # both bedrooms share the same switch

        except TimeOutException:
            pass  # didn't complete on time
