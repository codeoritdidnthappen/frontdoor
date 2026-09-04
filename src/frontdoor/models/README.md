# Bundled models

## face_detection_yunet_2023mar.onnx

YuNet face detection model, the primary detector in `frontdoor.faceblur`
(TICK-257 follow-up, #232). Committed into the repo (~230 KB) so runtime
needs no network and no download step.

- Source: the official OpenCV model zoo -
  <https://github.com/opencv/opencv_zoo>, path
  `models/face_detection_yunet/face_detection_yunet_2023mar.onnx`
- License: Apache-2.0 (per the opencv_zoo repository; the model card credits
  Shiqi Yu et al., libfacedetection)
- Loaded via `cv2.FaceDetectorYN`; requires opencv-python-headless >= 4.9
  (already pinned in pyproject.toml)
