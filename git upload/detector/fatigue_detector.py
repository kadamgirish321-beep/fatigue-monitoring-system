
# ==============================
# fatigue_detector.py (stable)
# ==============================

import os, sys, contextlib, time, math
import cv2
import numpy as np
from collections import deque
from db import insert_reading   # your DB function

# ---- Quiet most TF/MP logs (harmless warnings may still appear very early) ----
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "3"

@contextlib.contextmanager
def silence_stderr():
    old = sys.stderr
    try:
        with open(os.devnull, "w") as devnull:
            sys.stderr = devnull
            yield
    finally:
        sys.stderr = old

with silence_stderr():
    import mediapipe as mp

mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
mp_face = mp.solutions.face_mesh
mp_pose = mp.solutions.pose

# ----------------- constants -----------------
SMOOTH_WINDOW = 8
CALIBRATION_FRAMES = 60
EYE_CLOSE_TIME = 0.4
HEAD_TILT_THRESH = 15

# ----------------- helpers -----------------
def euclid(a, b):
    return np.linalg.norm(np.array([a.x, a.y]) - np.array([b.x, b.y]))

def eye_aspect_ratio(landmarks, eye_idx):
    p = [landmarks[i] for i in eye_idx]
    return (euclid(p[1], p[5]) + euclid(p[2], p[4])) / (2.0 * euclid(p[0], p[3]) + 1e-6)

def mouth_aspect_ratio(landmarks, mouth_idx):
    p = [landmarks[i] for i in mouth_idx]
    return (euclid(p[1], p[5]) + euclid(p[2], p[4])) / (2.0 * euclid(p[0], p[3]) + 1e-6)

class MovingAverage:
    def __init__(self, window): self.buf = deque(maxlen=window)
    def update(self, v): 
        self.buf.append(v); 
        return sum(self.buf)/len(self.buf)

def put_text(img, text, y, x=10):
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2, cv2.LINE_AA)

# ----------------- main -----------------
def main():
    user_id = "user123"

    # On Windows, CAP_DSHOW is often more reliable
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    # Optional: request a sane size
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    if not cap.isOpened():
        print("ERROR: Could not open webcam.")
        return

    # Create solutions (fast Pose; FaceMesh single face)
    with silence_stderr():
        face = mp_face.FaceMesh(
            max_num_faces=1,
            refine_landmarks=False,   # set True only if you need iris; slower
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        pose = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=0,       # 0 = fastest
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

    # Smoothers and calibration
    tilt_smoother = MovingAverage(SMOOTH_WINDOW)
    eye_smoother  = MovingAverage(SMOOTH_WINDOW)
    mouth_smoother= MovingAverage(SMOOTH_WINDOW)

    head_tilt_base = base_ear = base_mar = None
    frame_idx = 0
    fatigue_status = "Calibrating..."
    closed_start = None
    eye_closed = False
    blink_count = 0
    blink_rate = 0.0
    start_time = time.time()
    last_db_time = 0

    # Indices
    LEFT_EYE  = [33, 160, 158, 133, 153, 144]
    RIGHT_EYE = [362, 385, 387, 263, 373, 380]
    # More robust mouth set (outer vertical span)
    MOUTH = [61, 91, 291, 321, 13, 14]  # (left, upper, right, lower, top, bottom)

    prev = time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            print("WARN: empty frame from camera.")
            break

        # --- MediaPipe recommended pattern ---
        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image.flags.writeable = False
        face_result = face.process(image)
        pose_result = pose.process(image)
        image.flags.writeable = True  # back to writeable for drawing
        frame = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        detected_face = face_result.multi_face_landmarks is not None
        detected_pose = pose_result.pose_landmarks is not None

        # Draw overlays so you can SEE if it's working
        if detected_face:
            mp_drawing.draw_landmarks(
                frame,
                face_result.multi_face_landmarks[0],
                mp_face.FACEMESH_TESSELATION,
                landmark_drawing_spec=None,
                connection_drawing_spec=mp_drawing_styles
                    .get_default_face_mesh_tesselation_style()
            )
        if detected_pose:
            mp_drawing.draw_landmarks(
                frame,
                pose_result.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=mp_drawing_styles
                    .get_default_pose_landmarks_style()
            )

        if detected_face and detected_pose:
            face_lm = face_result.multi_face_landmarks[0].landmark
            pose_lm = pose_result.pose_landmarks.landmark

            ear = (eye_aspect_ratio(face_lm, LEFT_EYE) + eye_aspect_ratio(face_lm, RIGHT_EYE))/2
            ear_smooth = eye_smoother.update(ear)

            mar_smooth = mouth_smoother.update(mouth_aspect_ratio(face_lm, MOUTH))

            L_EAR = mp_pose.PoseLandmark.LEFT_EAR.value
            R_EAR = mp_pose.PoseLandmark.RIGHT_EAR.value
            dx = pose_lm[R_EAR].x - pose_lm[L_EAR].x
            dy = pose_lm[R_EAR].y - pose_lm[L_EAR].y
            tilt = abs(math.degrees(math.atan2(dy, dx)))
            tilt_smooth = tilt_smoother.update(tilt)

            # Calibration
            if frame_idx < CALIBRATION_FRAMES:
                base_ear = ear_smooth if base_ear is None else 0.9*base_ear + 0.1*ear_smooth
                base_mar = mar_smooth if base_mar is None else 0.9*base_mar + 0.1*mar_smooth
                head_tilt_base = tilt_smooth if head_tilt_base is None else 0.9*head_tilt_base + 0.1*tilt_smooth
                fatigue_status = "Calibrating..."
            else:
                EAR_THRESH = max(0.08, base_ear * 0.75)   # clamp to avoid zero
                MAR_THRESH = base_mar * 1.8

                now = time.time()

                # Blink detection
                if ear_smooth < EAR_THRESH:
                    if not eye_closed:
                        eye_closed = True
                else:
                    if eye_closed:
                        blink_count += 1
                    eye_closed = False

                # Prolonged closure
                if ear_smooth < EAR_THRESH:
                    if closed_start is None:
                        closed_start = now
                    elif now - closed_start > EYE_CLOSE_TIME:
                        fatigue_status = "Eyes closed — fatigue"
                else:
                    closed_start = None

                # Head tilt first (strong signal)
                if head_tilt_base is not None and abs(tilt_smooth - head_tilt_base) > HEAD_TILT_THRESH:
                    fatigue_status = "Head droop — drowsy"
                # Mouth open
                elif mar_smooth > MAR_THRESH:
                    fatigue_status = "Mouth open"
                else:
                    fatigue_status = "Normal"

                elapsed_min = (time.time() - start_time) / 60.0
                blink_rate = (blink_count / elapsed_min) if elapsed_min > 0 else 0.0

                # Write to DB at most 5 times per second to avoid thrashing
                if now - last_db_time > 0.2:
                    insert_reading(user_id, float(ear_smooth), float(mar_smooth),
                                   int(blink_count), float(blink_rate), str(fatigue_status))
                    last_db_time = now

            # On-screen metrics
            put_text(frame, f"EAR: {ear_smooth:.3f} | MAR: {mar_smooth:.3f} | Tilt: {tilt_smooth:.1f}", 30)
            put_text(frame, f"Status: {fatigue_status}", 60)

        else:
            # Help the user understand what's missing
            if not detected_face:
                put_text(frame, "Face: NOT DETECTED", 30)
            if not detected_pose:
                put_text(frame, "Pose: NOT DETECTED", 60)

        # FPS
        now = time.time()
        fps = 1.0 / max(1e-6, (now - prev))
        prev = now
        put_text(frame, f"FPS: {fps:.1f}", 90)

        cv2.imshow("Fatigue Detector (FaceMesh + Pose)", frame)
        frame_idx += 1
        if cv2.waitKey(1) & 0xFF == 27:  # ESC to exit
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
