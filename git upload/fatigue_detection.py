import cv2
import mediapipe as mp
import numpy as np
import time
from collections import deque
import math

mp_drawing = mp.solutions.drawing_utils
mp_face = mp.solutions.face_mesh
mp_pose = mp.solutions.pose

# ---------- HYPERPARAMETERS ----------
SMOOTH_WINDOW = 8
CALIBRATION_FRAMES = 60
EYE_CLOSE_TIME = 0.4
HEAD_TILT_THRESH = 15
# -------------------------------------

def euclid(a, b):
    return np.linalg.norm(np.array([a.x, a.y]) - np.array([b.x, b.y]))

# Eye Aspect Ratio (EAR)
def eye_aspect_ratio(landmarks, eye_indices):
    p = [landmarks[i] for i in eye_indices]
    return (euclid(p[1], p[5]) + euclid(p[2], p[4])) / (2.0 * euclid(p[0], p[3]) + 1e-6)

# Mouth Aspect Ratio (MAR)
def mouth_aspect_ratio(landmarks, mouth_indices):
    p = [landmarks[i] for i in mouth_indices]
    return (euclid(p[1], p[5]) + euclid(p[2], p[4])) / (2.0 * euclid(p[0], p[3]) + 1e-6)

class MovingAverage:
    def __init__(self, window):
        self.buf = deque(maxlen=window)
    def update(self, val):
        self.buf.append(val)
        return sum(self.buf) / len(self.buf)

def main():
    cap = cv2.VideoCapture(0)
    face = mp_face.FaceMesh(refine_landmarks=True, max_num_faces=1)
    pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)

    # Baselines
    head_tilt_base = None
    base_ear = None
    base_mar = None

    # Smoothers
    tilt_smoother = MovingAverage(SMOOTH_WINDOW)
    eye_smoother = MovingAverage(SMOOTH_WINDOW)
    mouth_smoother = MovingAverage(SMOOTH_WINDOW)

    frame_idx = 0
    fatigue_status = "Calibrating..."
    closed_start = None
    blink_in_progress = False
    blink_count = 0
    blink_rate = 0.0

    start_time = time.time()  
   

    print("Calibrating neutral head, eyes, and mouth...")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_result = face.process(rgb)
        pose_result = pose.process(rgb)

        if face_result.multi_face_landmarks and pose_result.pose_landmarks:
            face_lm = face_result.multi_face_landmarks[0].landmark
            pose_lm = pose_result.pose_landmarks.landmark

            # Eye indices
            LEFT_EYE = [33, 160, 158, 133, 153, 144]
            RIGHT_EYE = [362, 385, 387, 263, 373, 380]
            leftEAR = eye_aspect_ratio(face_lm, LEFT_EYE)
            rightEAR = eye_aspect_ratio(face_lm, RIGHT_EYE)
            ear = (leftEAR + rightEAR) / 2.0
            ear_smooth = eye_smoother.update(ear)

            # Mouth indices
            MOUTH = [61, 81, 311, 178, 13, 14]
            mar = mouth_aspect_ratio(face_lm, MOUTH)
            mar_smooth = mouth_smoother.update(mar)

            # Head tilt
            L_EAR = mp_pose.PoseLandmark.LEFT_EAR.value
            R_EAR = mp_pose.PoseLandmark.RIGHT_EAR.value
            left_ear = np.array([pose_lm[L_EAR].x, pose_lm[L_EAR].y])
            right_ear = np.array([pose_lm[R_EAR].x, pose_lm[R_EAR].y])
            dx, dy = right_ear - left_ear
            tilt_angle = abs(math.degrees(math.atan2(dy, dx)))
            tilt_smooth = tilt_smoother.update(tilt_angle)

            # ---------------- Calibration ----------------
            if frame_idx < CALIBRATION_FRAMES:
                # Baseline averages
                base_ear = ear_smooth if base_ear is None else 0.9 * base_ear + 0.1 * ear_smooth
                base_mar = mar_smooth if base_mar is None else 0.9 * base_mar + 0.1 * mar_smooth
                head_tilt_base = tilt_smooth if head_tilt_base is None else 0.9 * head_tilt_base + 0.1 * tilt_smooth
                fatigue_status = f"Calibrating... ({frame_idx+1}/{CALIBRATION_FRAMES})"
            else:
                EAR_THRESH = base_ear * 0.75
                MAR_THRESH = base_mar * 1.8  # Adaptive threshold — mouth open only if 80% wider than baseline

                # Blink detection
                if ear_smooth < EAR_THRESH and not blink_in_progress:
                    blink_in_progress = True
                    blink_start_time = time.time()
                elif ear_smooth >= EAR_THRESH and blink_in_progress:
                    blink_duration = time.time() - blink_start_time
                    if 0.08 <= blink_duration <= 0.4:
                        blink_count += 1
                    blink_in_progress = False
                elapsed_minutes = (time.time() - start_time) / 60
                if elapsed_minutes > 0:
                    blink_rate = blink_count / elapsed_minutes
                else:
                    blink_rate = 0

                # Fatigue from closed eyes
                now = time.time()
                if ear_smooth < EAR_THRESH:
                    if closed_start is None:
                        closed_start = now
                    elif now - closed_start > EYE_CLOSE_TIME:
                        fatigue_status = "Eyes closed — fatigue"
                else:
                    closed_start = None

                # Head droop
                if abs(tilt_smooth - head_tilt_base) > HEAD_TILT_THRESH:
                    fatigue_status = "Head droop — drowsy"
                # Mouth open
                elif mar_smooth > MAR_THRESH:
                    fatigue_status = "Mouth open"
                else:
                    fatigue_status = "Normal"

            # Drawing
            cv2.putText(frame, f"EAR: {ear_smooth:.3f}", (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
            cv2.putText(frame, f"MAR: {mar_smooth:.3f}", (150, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
            cv2.putText(frame, f"Blinks: {blink_count}", (300, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
            cv2.putText(frame, f"Blinks/min: {blink_rate:.1f}", (400, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200,200,200), 1)
            cv2.putText(frame, fatigue_status, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2)
            
        else:
            cv2.putText(frame, "No face detected", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)

        cv2.imshow("Fatigue + Mouth Open Detector", frame)
        frame_idx += 1

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
