import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import esp32, text_sensor
from esphome.const import CONF_ID, CONF_SENSOR_ID

DEPENDENCIES = ["esp32_camera"]
AUTO_LOAD = ["text_sensor"]

litter_robot_presence_detector_ns = cg.esphome_ns.namespace(
    "litter_robot_presence_detector"
)
LitterRobotPresenceDetectorConstructor = litter_robot_presence_detector_ns.class_(
    "LitterRobotPresenceDetector", cg.Component, text_sensor.TextSensor
)

# MULTI_CONF = True
CONF_USE_EMA = "use_ema"

CONFIG_SCHEMA = (
    text_sensor.text_sensor_schema(LitterRobotPresenceDetectorConstructor)
    .extend(
        {
            cv.GenerateID(): cv.declare_id(LitterRobotPresenceDetectorConstructor),
            # cv.Required(CONF_SENSOR_ID): cv.use_id(sensor.Sensor)
            cv.Optional(
                CONF_USE_EMA
            ): cv.boolean_false,  # Exponential Moving Average vs Simple Moving Average
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
)


async def to_code(config):
    var = await text_sensor.new_text_sensor(config)
    # cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    esp32.add_idf_component(
        name="litter_robot_detect",
        repo="https://github.com/khaiql/my-idf-component",
        ref="main",
        path="litter_robot_detect",
        refresh=0,
    )

    # version 1.3.1 doesn't run into incompatible compiler standard
    esp32.add_idf_component(name="espressif/esp-tflite-micro", ref="1.3.1")

    esp32.add_idf_sdkconfig_option("LITTER_ROBOT_MODEL_TFLITE", "y")
    # Force Malloc to use PSRAM so your 1MB arena doesn't hit Internal RAM
    esp32.add_idf_sdkconfig_option("CONFIG_SPIRAM_USE_MALLOC", True)
    # Ensure large allocations (like the arena) go to PSRAM
    esp32.add_idf_sdkconfig_option("CONFIG_SPIRAM_MALLOC_ALWAYSINTERNAL", 4096)
