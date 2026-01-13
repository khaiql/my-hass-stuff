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

    esp32.add_idf_component(name="espressif/esp-tflite-micro", ref="1.3.5")

    esp32.add_idf_component(name="espressif/esp_jpeg", ref="1.3.1")

    if config[CONF_USE_EMA]:
        cg.add_define("USE_EMA")

    # inferrence could take a long time, set Watchdog timeout to 10s
    esp32.add_idf_sdkconfig_option("CONFIG_ESP_TASK_WDT_TIMEOUT_S", 20)

    cg.add_build_flag("-DTF_LITE_STATIC_MEMORY")
    cg.add_build_flag("-DTF_LITE_DISABLE_X86_NEON")
    # cg.add_build_flag("-DESP_NN")
    cg.add_build_flag("-DNN_OPTIMIZATIONS")
