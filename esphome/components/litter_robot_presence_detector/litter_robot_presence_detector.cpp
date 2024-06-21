#ifdef USE_ESP32
#include "litter_robot_presence_detector.h"
#include "esphome/core/log.h"

#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "person_detect_model_data.h"
#include <time.h>

#ifdef USE_IMG_CONVERTERS
#include "img_converters.h"
#else
#include "jpeg_decoder.h"
#endif

namespace esphome {
namespace litter_robot_presence_detector {

static const char *const TAG = "litter_robot_presence_detector";
static const uint32_t MODEL_ARENA_SIZE = 200 * 1024;
static const uint32_t INPUT_BUFFER_SIZE = 144 * 176 * 3 * sizeof(uint8_t);

float LitterRobotPresenceDetector::get_setup_priority() const { return setup_priority::AFTER_CONNECTION; }

void LitterRobotPresenceDetector::on_shutdown() {
  this->image_ = nullptr;
  vSemaphoreDelete(this->semaphore_);
  this->semaphore_ = nullptr;
}

bool LitterRobotPresenceDetector::register_preprocessor_ops(tflite::MicroMutableOpResolver<9> &micro_op_resolver) {
  if (micro_op_resolver.AddConv2D() != kTfLiteOk) {
    ESP_LOGE(TAG, "failed to register ops AddConv2D");
    return false;
  }

  if (micro_op_resolver.AddQuantize() != kTfLiteOk) {
    ESP_LOGE(TAG, "failed to register ops AddQuantize");
    return false;
  }

  if (micro_op_resolver.AddLeakyRelu() != kTfLiteOk) {
    ESP_LOGE(TAG, "failed to register ops AddLeakyRelu");
    return false;
  }

  if (micro_op_resolver.AddMaxPool2D() != kTfLiteOk) {
    ESP_LOGE(TAG, "failed to register ops AddMaxPool2D");
    return false;
  }

  if (micro_op_resolver.AddFullyConnected() != kTfLiteOk) {
    ESP_LOGE(TAG, "failed to register ops AddFullyConnected");
    return false;
  }

  if (micro_op_resolver.AddReshape() != kTfLiteOk) {
    ESP_LOGE(TAG, "failed to register ops AddReshape");
    return false;
  }

  if (micro_op_resolver.AddSoftmax() != kTfLiteOk) {
    ESP_LOGE(TAG, "failed to register ops AddSoftmax");
    return false;
  }

  if (micro_op_resolver.AddMean() != kTfLiteOk) {
    ESP_LOGE(TAG, "failed to register ops AddMean");
    return false;
  }

  return true;
}

bool LitterRobotPresenceDetector::decode_jpg(camera_fb_t *rb) {
#ifdef USE_IMG_CONVERTERS
  if (!fmt2rgb888(rb->buf, rb->len, PIXFORMAT_RGB888, this->input_buffer)) {
    ESP_LOGE(TAG, "cant decode to rgb");
    return false;
  }

  ESP_LOGD(TAG, "decoded to jpg");
#else
  esp_jpeg_image_cfg_t jpeg_cfg = {.indata = (uint8_t *) rb->buf,
                                   .indata_size = rb->len,
                                   .outbuf = this->input_buffer,
                                   .outbuf_size = rb->width * rb->height * 3 * sizeof(uint16_t),
                                   .out_format = JPEG_IMAGE_FORMAT_RGB888,
                                   .out_scale = JPEG_IMAGE_SCALE_0,
                                   .flags = {
                                       .swap_color_bytes = 0,
                                   }};
  esp_jpeg_image_output_t outimg;

  esp_err_t res = esp_jpeg_decode(&jpeg_cfg, &outimg);
  if (res != ESP_OK) {
    return false;
  }

  ESP_LOGD(TAG, "out img width=%d height=%d", outimg.width, outimg.height);
#endif

  return true;
}

bool LitterRobotPresenceDetector::setup_model() {
  ExternalRAMAllocator<uint8_t> arena_allocator(ExternalRAMAllocator<uint8_t>::ALLOW_FAILURE);
  this->tensor_arena_ = arena_allocator.allocate(MODEL_ARENA_SIZE);
  if (this->tensor_arena_ == nullptr) {
    ESP_LOGE(TAG, "Could not allocate the streaming model's tensor arena.");
    return false;
  }

  ExternalRAMAllocator<uint8_t> input_buffer_allocator(ExternalRAMAllocator<uint8_t>::ALLOW_FAILURE);
  this->input_buffer = input_buffer_allocator.allocate(INPUT_BUFFER_SIZE);
  if (this->input_buffer == nullptr) {
    ESP_LOGE(TAG, "Could not allocate input buffer.");
    return false;
  }

  this->model = ::tflite::GetModel(g_person_detect_model_data);
  if (this->model->version() != TFLITE_SCHEMA_VERSION) {
    ESP_LOGE(TAG,
             "Model provided is schema version %d not equal "
             "to supported version %d.\n",
             model->version(), TFLITE_SCHEMA_VERSION);
    return false;
  }

  static tflite::MicroMutableOpResolver<9> micro_op_resolver;
  if (!this->register_preprocessor_ops(micro_op_resolver)) {
    ESP_LOGE(TAG, "Register ops failed");
    return false;
  }

  static tflite::MicroInterpreter static_interpreter(this->model, micro_op_resolver, this->tensor_arena_,
                                                     MODEL_ARENA_SIZE);
  this->interpreter = &static_interpreter;

  TfLiteStatus allocate_status = interpreter->AllocateTensors();
  if (allocate_status != kTfLiteOk) {
    ESP_LOGE(TAG, "AllocateTensors() failed");
    return false;
  }

  ESP_LOGD(TAG, "setup model successfully");

  return true;
}

void LitterRobotPresenceDetector::setup() {
  ESP_LOGD(TAG, "Begin setup");

  // SETUP CAMERA
  if (!esp32_camera::global_esp32_camera || esp32_camera::global_esp32_camera->is_failed()) {
    ESP_LOGW(TAG, "setup litter robot presence detector failed");
    this->mark_failed();
    return;
  }

  if (!this->setup_model()) {
    ESP_LOGE(TAG, "setup model failed");
    this->mark_failed();
    return;
  }

  this->semaphore_ = xSemaphoreCreateBinary();

  esp32_camera::global_esp32_camera->add_image_callback([this](std::shared_ptr<esp32_camera::CameraImage> image) {
    ESP_LOGD(TAG, "received image");
    if (image->was_requested_by(esp32_camera::API_REQUESTER)) {
      this->image_ = std::move(image);
      xSemaphoreGive(this->semaphore_);
    }
  });

  ESP_LOGD(TAG, "setup litter robot presence detector successfully");
}

void LitterRobotPresenceDetector::loop() {
  if (!this->is_ready()) {
    ESP_LOGW(TAG, "not ready yet, skip!");
    return;
  }

  esp32_camera::global_esp32_camera->request_image(esphome::esp32_camera::API_REQUESTER);
  auto image = this->wait_for_image_();

  if (!image) {
    ESP_LOGW(TAG, "SNAPSHOT: failed to acquire frame");
    return;
  }
  this->image_ = nullptr;

  if (!this->start_infer(image)) {
    ESP_LOGE(TAG, "infer failed");
  } else {
    bool detected = this->get_prediction_result();
    ESP_LOGI(TAG, "predicted class %s", detected ? "true" : "false");
    this->publish_state(detected);
  }
}

void LitterRobotPresenceDetector::dump_config() {
  if (this->is_failed()) {
    ESP_LOGE(TAG, "  Setup Failed");
    return;
  }
  TfLiteTensor *input = this->interpreter->input(0);
  TfLiteTensor *output = this->interpreter->output(0);

  ESP_LOGCONFIG(TAG, "Input");
  ESP_LOGCONFIG(TAG, "  - dim_size: %d", input->dims->size);
  ESP_LOGCONFIG(TAG, "  - input_dims (%d,%d,%d,%d)", input->dims->data[0], input->dims->data[1], input->dims->data[2],
                input->dims->data[3]);
  ESP_LOGCONFIG(TAG, "  - zero_point=%d scale=%f", input->params.zero_point, input->params.scale);
  ESP_LOGCONFIG(TAG, "  - input_type: %d", input->type);
  ESP_LOGCONFIG(TAG, "Output");
  ESP_LOGCONFIG(TAG, "  - dim_size: %d", output->dims->size);
  ESP_LOGCONFIG(TAG, "  - dims (%d,%d)", output->dims->data[0], output->dims->data[1]);
  ESP_LOGCONFIG(TAG, "  - zero_point=%d scale=%f", output->params.zero_point, output->params.scale);
  ESP_LOGCONFIG(TAG, "  - output_type: %d", output->type);
}

std::shared_ptr<esphome::esp32_camera::CameraImage> LitterRobotPresenceDetector::wait_for_image_() {
  std::shared_ptr<esphome::esp32_camera::CameraImage> image;
  image.swap(this->image_);

  if (!image) {
    // retry as we might still be fetching image
    xSemaphoreTake(this->semaphore_, 100);
    image.swap(this->image_);
  }

  return image;
}
bool LitterRobotPresenceDetector::start_infer(std::shared_ptr<esphome::esp32_camera::CameraImage> image) {
  camera_fb_t *rb = image->get_raw_buffer();

  TfLiteTensor *input = this->interpreter->input(0);
  size_t bytes_to_copy = input->bytes;
  uint32_t prior_invoke = millis();
  if (!this->decode_jpg(rb)) {
    ESP_LOGE(TAG, "cant decode to rgb");
    return false;
  }

  memcpy(input->data.uint8, this->input_buffer, bytes_to_copy);
  TfLiteStatus invokeStatus = this->interpreter->Invoke();
  ESP_LOGD(TAG, " Inference Latency=%u ms", (millis() - prior_invoke));
  return invokeStatus == kTfLiteOk;
}

bool LitterRobotPresenceDetector::get_prediction_result() {
  TfLiteTensor *output = this->interpreter->output(0);

  auto empty_score = output->data.uint8[0];
  auto cat_detected_score = output->data.uint8[1];
  ESP_LOGD(TAG, "empty score=%d cat_detected score=%d", empty_score, cat_detected_score);

#ifndef USE_EMA
  bool is_detected = cat_detected_score > empty_score;

  this->prediction_history[this->last_index] = is_detected ? 1 : 0;
  this->last_index += 1;
  if (this->last_index == PREDICTION_HISTORY_SIZE) {
    this->last_index = 0;
  }

  uint8_t sum = 0;
  for (int i = 0; i < PREDICTION_HISTORY_SIZE; i++) {
    sum += this->prediction_history[i];
  }
  float avg = sum / static_cast<float>(PREDICTION_HISTORY_SIZE);
  return avg >= 0.5;
#else
  double new_value = cat_detected_score > empty_score ? 1 : 0;
  this->current_prediction = this->ema_alpha * new_value + (1 - this->ema_alpha) * this->current_prediction;
  return this->current_prediction >= 0.5;
#endif
}
}  // namespace litter_robot_presence_detector
}  // namespace esphome
#endif
