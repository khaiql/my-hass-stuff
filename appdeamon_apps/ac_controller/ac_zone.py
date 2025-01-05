SETTING_DELAY_DURATION_SECOND = 2


class Zone:
    def __init__(self, adapi, name, config={}):
        self.adapi = adapi
        self.name = name

        self.priority = int(config["priority"]) if "priority" in config else 1
        self.temperature_sensor = (
            self.adapi.get_entity(config["temperature_entity_id"])
            if "temperature_entity_id" in config
            else None
        )
        self.fingerbot_switch = self.adapi.get_entity(
            config["switch_entity_id"]
        )  # Required
        self.zone_state = self.adapi.get_entity(config["state_entity_id"])  # Required
        self.fingerbot_switch_reverse = (
            self.adapi.get_entity(config["switch_reverse_entity_id"])
            if "switch_reverse_entity_id" in config
            else None
        )

        self.desired_temperature_setting_entity = (
            self.adapi.get_entity(config["desired_temperature_entity_id"])
            if "desired_temperature_entity_id" in config
            else None
        )
        self.threshold_entity = (
            self.adapi.get_entity(config["threshold_entity_id"])
            if "threshold_entity_id" in config
            else None
        )

    async def is_ac_controlled(self):
        return await self.zone_state.is_state("on")

    async def is_running(self):
        return await self.is_switch_state("on")

    async def is_switch_state(self, state: str):
        return await self.fingerbot_switch.is_state(state)

    async def get_current_temperature(self):
        return (
            float(await self.temperature_sensor.get_state())
            if self.temperature_sensor
            else None
        )

    async def get_desired_temperature(self, global_setting=None):
        if self.desired_temperature_setting_entity:
            return float(await self.desired_temperature_setting_entity.get_state())
        return global_setting

    async def get_threshold(self, global_setting=None):
        if self.threshold_entity:
            return float(await self.threshold_entity.get_state())
        return global_setting

    async def has_reached_desired_temp(
        self, global_desired_temperature, mode="heating"
    ):
        current_temp = await self.get_current_temperature()
        desired_temperature = await self.get_desired_temperature(
            global_setting=global_desired_temperature
        )
        if mode == "heating":
            return current_temp >= desired_temperature

        return current_temp <= desired_temperature  # cooling mode

    async def is_out_of_desired_temp(
        self, global_desired_temperature, global_threshold, mode="heating"
    ):
        current_temp = await self.get_current_temperature()
        desired_temperature = await self.get_desired_temperature(
            global_setting=global_desired_temperature
        )
        threshold = await self.get_threshold(global_setting=global_threshold)

        print(
            f"is_out_of_desired_temp zone={self.name} {current_temp=} {desired_temperature=} {threshold=} {mode=}"
        )

        if mode == "heating":
            return current_temp < desired_temperature - threshold

        return current_temp > desired_temperature + threshold

    async def revert_switch_state_without_clicking(self):
        if self.fingerbot_switch_reverse:
            await self.fingerbot_switch_reverse.toggle()
        else:
            new_state = "off" if await self.fingerbot_switch.is_state("on") else "on"
            await self.fingerbot_switch.set_state(state=new_state)

    async def toggle_switch_and_wait_state(
        self, expected_state: str, timeout: int = 10
    ):
        await self.fingerbot_switch.toggle()
        await self.fingerbot_switch.wait_state(expected_state, timeout=timeout)

    def has_entity(self, entity_id):
        return entity_id in [
            self.temperature_sensor.entity_id,
            self.zone_state.entity_id,
        ]

    def listen_state(self, callback):
        self.zone_state.listen_state(callback)

        if self.temperature_sensor:
            self.temperature_sensor.listen_state(callback)
        if self.desired_temperature_setting_entity is not None:
            self.desired_temperature_setting_entity.listen_state(
                callback, duration=SETTING_DELAY_DURATION_SECOND
            )
        if self.threshold_entity is not None:
            self.threshold_entity.listen_state(
                callback, duration=SETTING_DELAY_DURATION_SECOND
            )

    def __str__(self):
        return f"{self.name} priority={self.priority} active={self.is_ac_controlled()} switch_state={self.fingerbot_switch.get_state()} current_temp={self.get_current_temperature()}"
