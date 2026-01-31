import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import pins
from esphome.components import i2c, sensor, binary_sensor
from esphome.const import (
    CONF_GAIN,
    CONF_ID,
    CONF_INTERRUPT_PIN,
    CONF_RESOLUTION,
)

DEPENDENCIES = ["i2c"]
AUTO_LOAD = ["binary_sensor"]

CONF_MEASUREMENT_RATE = "measurement_rate"
CONF_THRESHOLD_HIGH = "threshold_high"
CONF_THRESHOLD_LOW = "threshold_low"
CONF_IR_LED_PIN = "ir_led_pin"
CONF_IR_LED_STATUS = "ir_led_status"

dfrobot_ltr308_ns = cg.esphome_ns.namespace("dfrobot_ltr308")
DFRobotLTR308Component = dfrobot_ltr308_ns.class_(
    "DFRobotLTR308Component", cg.PollingComponent, sensor.Sensor, i2c.I2CDevice
)

DFRobotLTR308Gain = dfrobot_ltr308_ns.enum("DFRobotLTR308Gain")
GAINS = {
    "1X": DFRobotLTR308Gain.GAIN_1X,
    "3X": DFRobotLTR308Gain.GAIN_3X,
    "6X": DFRobotLTR308Gain.GAIN_6X,
    "9X": DFRobotLTR308Gain.GAIN_9X,
    "18X": DFRobotLTR308Gain.GAIN_18X,
}

DFRobotLTR308Resolution = dfrobot_ltr308_ns.enum("DFRobotLTR308Resolution")
RESOLUTIONS = {
    "400ms": DFRobotLTR308Resolution.RES_400MS_20B,
    "200ms": DFRobotLTR308Resolution.RES_200MS_19B,
    "100ms": DFRobotLTR308Resolution.RES_100MS_18B,
    "50ms": DFRobotLTR308Resolution.RES_50MS_17B,
    "25ms": DFRobotLTR308Resolution.RES_25MS_16B,
}

DFRobotLTR308Rate = dfrobot_ltr308_ns.enum("DFRobotLTR308Rate")
RATES = {
    "25ms": DFRobotLTR308Rate.RATE_25MS,
    "50ms": DFRobotLTR308Rate.RATE_50MS,
    "100ms": DFRobotLTR308Rate.RATE_100MS,
    "500ms": DFRobotLTR308Rate.RATE_500MS,
    "1000ms": DFRobotLTR308Rate.RATE_1000MS,
    "2000ms": DFRobotLTR308Rate.RATE_2000MS,
}


CONFIG_SCHEMA = (
    sensor.sensor_schema(DFRobotLTR308Component, unit_of_measurement="lux", icon="mdi:brightness-5", accuracy_decimals=2)
    .extend(
        {
            cv.Optional(CONF_GAIN, default="3X"): cv.enum(GAINS, upper=True),
            cv.Optional(CONF_RESOLUTION, default="100ms"): cv.enum(RESOLUTIONS),
            cv.Optional(CONF_MEASUREMENT_RATE, default="100ms"): cv.enum(RATES),
            cv.Optional(CONF_THRESHOLD_HIGH, default=500.0): cv.float_,
            cv.Optional(CONF_THRESHOLD_LOW, default=10.0): cv.float_,
            cv.Optional(CONF_INTERRUPT_PIN): pins.internal_gpio_input_pin_schema,
            cv.Optional(CONF_IR_LED_PIN): pins.internal_gpio_output_pin_schema,
            cv.Optional(CONF_IR_LED_STATUS): binary_sensor.binary_sensor_schema(),
        }
    )
    .extend(cv.polling_component_schema("60s"))
    .extend(i2c.i2c_device_schema(0x53))
)


async def to_code(config):
    var = await sensor.new_sensor(config)
    await cg.register_component(var, config)
    await i2c.register_i2c_device(var, config)

    cg.add(var.set_gain(config[CONF_GAIN]))
    cg.add(var.set_resolution(config[CONF_RESOLUTION]))
    cg.add(var.set_rate(config[CONF_MEASUREMENT_RATE]))
    cg.add(var.set_threshold_high(config[CONF_THRESHOLD_HIGH]))
    cg.add(var.set_threshold_low(config[CONF_THRESHOLD_LOW]))

    if CONF_INTERRUPT_PIN in config:
        interrupt_pin = await cg.gpio_pin_expression(config[CONF_INTERRUPT_PIN])
        cg.add(var.set_interrupt_pin(interrupt_pin))
    if CONF_IR_LED_PIN in config:
        ir_led_pin = await cg.gpio_pin_expression(config[CONF_IR_LED_PIN])
        cg.add(var.set_ir_led_pin(ir_led_pin))
    if CONF_IR_LED_STATUS in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_IR_LED_STATUS])
        cg.add(var.set_ir_led_status_sensor(sens))
