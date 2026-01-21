#include "litter_robot_presence_detector.h"
#include "esphome/core/log.h"
#include "freertos/idf_additions.h"

namespace esphome {
namespace litter_robot_presence_detector {

static const char *const TAG = "litter_robot_presence_detector";
static const uint32_t MODEL_ARENA_SIZE = 500 * 1024;

#define INFERENCE_IDLE_BIT BIT0
#define INFERENCE_IN_PROGRESS_BIT BIT1

float LitterRobotPresenceDetector::get_setup_priority() const { return setup_priority::LATE; }

void LitterRobotPresenceDetector::on_shutdown() {
  this->image_ = nullptr;
  if (this->inference_task_handle_ != nullptr) {
    vTaskDelete(this->inference_task_handle_);
    this->inference_task_handle_ = nullptr;
  }
  vSemaphoreDelete(this->semaphore);
  this->semaphore = nullptr;
}

void LitterRobotPresenceDetector::inference_task_trampoline(void *params) {
  LitterRobotPresenceDetector *detector = (LitterRobotPresenceDetector *) params;
  while (1) {
    if (xSemaphoreTake(detector->semaphore, portMAX_DELAY) == pdTRUE) {
      detector->inference_task();
    }
  }
}

void LitterRobotPresenceDetector::inference_task() {
  // Signal that an inference task is on going
  xEventGroupClearBits(inference_event_group, INFERENCE_IDLE_BIT);
  xEventGroupSetBits(inference_event_group, INFERENCE_IN_PROGRESS_BIT);

  std::shared_ptr<esphome::camera::CameraImage> local_image;
  {
    std::lock_guard<std::mutex> lock(this->image_mutex_);
    local_image = this->image_;
  }

  auto camera_image = std::static_pointer_cast<esp32_camera::ESP32CameraImage>(local_image);
  if (camera_image) {
    camera_fb_t *fb = camera_image->get_raw_buffer();

    uint32_t start_time = esp_log_timestamp();
    this->prediction_result = this->cat_detector->run_inference(fb);
    uint32_t end_time = esp_log_timestamp();
    ESP_LOGI(TAG, "inference took %dms", end_time - start_time);
    if (this->prediction_result.err != ESP_OK) {
      ESP_LOGI(TAG, "Inference task failed");
    } else {
      this->publish_state(this->prediction_result.predicted_class.c_str());
    }
  }
  xEventGroupClearBits(this->inference_event_group, INFERENCE_IN_PROGRESS_BIT);
  xEventGroupSetBits(this->inference_event_group, INFERENCE_IDLE_BIT);

  // Clear the image_ pointer to release memory
  {
    std::lock_guard<std::mutex> lock(this->image_mutex_);
    this->image_ = nullptr;
  }
}

void LitterRobotPresenceDetector::setup() {
  ESP_LOGI(TAG, "Begin setup");

  // SETUP CAMERA
  if (!camera::Camera::instance() || camera::Camera::instance()->is_failed()) {
    ESP_LOGW(TAG, "setup litter robot presence detector failed");
    this->mark_failed();
    return;
  }

  camera_instance = (esp32_camera::ESP32Camera *) camera::Camera::instance();

  esp_err_t err;
  cat_detector = new ::litter_robot_detect::CatDetect();
  err = cat_detector->setup(MODEL_ARENA_SIZE);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "cat detector setup failed");
    this->mark_failed();
    return;
  }

  this->semaphore = xSemaphoreCreateBinary();
  this->inference_event_group = xEventGroupCreate();

  this->camera_instance = camera::Camera::instance();
  this->camera_instance->add_listener(this);
  xEventGroupSetBits(this->inference_event_group, INFERENCE_IDLE_BIT);

  // Create inference task on Core 1 (App Core) with 8KB stack
  xTaskCreatePinnedToCore(inference_task_trampoline, "inference_task", 8192 * 2, this, 5, &this->inference_task_handle_,
                          1);

  ESP_LOGD(TAG, "setup litter robot presence detector successfully");
}

void LitterRobotPresenceDetector::on_camera_image(const std::shared_ptr<camera::CameraImage> &image) {
  ESP_LOGD(TAG, "received image from %s", image->was_requested_by(camera::API_REQUESTER) ? "API_REQUESTER" : "OTHER");
  if (image->was_requested_by(esphome::camera::API_REQUESTER)) {
    EventBits_t current_bit = xEventGroupGetBits(inference_event_group);

    // Skip this frame
    if (current_bit == INFERENCE_IN_PROGRESS_BIT) {
      return;
    }

    // Assign the last frame
    {
      std::lock_guard<std::mutex> lock(this->image_mutex_);
      this->image_ = image;
    }
    xSemaphoreGive(semaphore);
  }
}

void LitterRobotPresenceDetector::loop() {
  if (this->camera_instance) {
    // Check if IDLE bit is set without waiting (0 tick delay)
    EventBits_t bits = xEventGroupGetBits(this->inference_event_group);

    if (bits & INFERENCE_IDLE_BIT) {
      // Clear the idle bit so we don't request 1000 times per second
      xEventGroupClearBits(this->inference_event_group, INFERENCE_IDLE_BIT);
      this->camera_instance->request_image(esphome::camera::API_REQUESTER);
    }
  }
}

void LitterRobotPresenceDetector::dump_config() {
  if (this->is_failed()) {
    ESP_LOGE(TAG, "  Setup Failed");
    return;
  }
}

}  // namespace litter_robot_presence_detector
}  // namespace esphome
