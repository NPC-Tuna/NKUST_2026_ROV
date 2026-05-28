import socket
import threading
import time
import os
import sys
import board
import busio
from adafruit_pca9685 import PCA9685
from gpiozero import Servo
import numpy as np

# Force stable hardware V4L2 hooks
os.environ["OPENCV_VIDEOIO_PRIORITY_V4L2"] = "10"
import cv2

# --- CONFIGURATION ---
CAM_INDEX_1 = 0  # Camera 1 (e.g., Front View)
CAM_INDEX_2 = 4  # Camera 2 (e.g., Gripper View)

NEUTRAL = 1.65
PWM_MAX = 1.9
PWM_MIN = 1.4
MAX_THRUST = 0.25
ASCEND_PWM = 1.8
DESCEND_PWM = 1.5

GRIPPER_PIN = 14     
GRIPPER_MAX = 1.0     
GRIPPER_MIN = -1.0    
GRIPPER_SPEED = 0.08  

H_MOT_LF = 0
H_MOT_RF = 1
H_MOT_LR = 2
H_MOT_RR = 3

V_MOT_LF = 7
V_MOT_RF = 4
V_MOT_LR = 6
V_MOT_RR = 5

JOY_LX_IDX = 1
JOY_LY_IDX = 2
JOY_RX_IDX = 3
JOY_RY_IDX = 4
KEY_A_IDX = 5       
KEY_D_IDX = 6       
BTN_RESET_IDX = 7   
BTN_AUTO_RET_IDX = 8 
BTN_ASCEND_IDX = 15 
BTN_DESCEND_IDX = 16
BTN_DISCON_IDX = 17

# --- GLOBAL STATE ---
state_lock = threading.Lock() 
state = {
    "h_pwms": [NEUTRAL] * 4,
    "v_base": NEUTRAL,
    "running": True,
    "gripper_target_pwm": GRIPPER_MIN, 
    "gripper_pwm": GRIPPER_MIN,        
    "last_heartbeat": time.time()       
}

# --- HARDWARE INITIALIZATION ---
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    pca = PCA9685(i2c)
    pca.frequency = 50
    print("Hardware initialized: PCA9685 OK.")
    
    gripper = Servo(GRIPPER_PIN, min_pulse_width=500/1000000, max_pulse_width=2500/1000000)
    print("Hardware initialized: Raspberry Pi GPIO14 OK.")
except Exception as e:
    print(f"Init failed: {e}")
    exit()

def set_pwm(ch, ms):
    ms = max(min(ms, PWM_MAX), PWM_MIN)
    duty = int((ms / 20.0) * 65535)
    pca.channels[ch].duty_cycle = duty

# --- BACKGROUND MOTOR CONTROL LOOP ---
def motor_control_thread():
    print("Control engine active.")
    while True:
        with state_lock:
            if not state["running"]:
                break
            if time.time() - state["last_heartbeat"] > 1.5:
                state["h_pwms"] = [NEUTRAL] * 4
                state["v_base"] = NEUTRAL
        
        with state_lock:
            v_base = state["v_base"]
            h_pwms = state["h_pwms"].copy()
            gripper_tgt = state["gripper_target_pwm"]
            gripper_pwm = state["gripper_pwm"]
            
        set_pwm(V_MOT_LF, v_base)
        set_pwm(V_MOT_RF, v_base)
        set_pwm(V_MOT_LR, v_base)
        set_pwm(V_MOT_RR, v_base)
        
        set_pwm(H_MOT_LF, h_pwms[0]) 
        set_pwm(H_MOT_RF, h_pwms[1]) 
        set_pwm(H_MOT_LR, h_pwms[2]) 
        set_pwm(H_MOT_RR, h_pwms[3]) 
        
        last_gripper_pwm = gripper_pwm
        if gripper_pwm < gripper_tgt:
            gripper_pwm = min(gripper_pwm + GRIPPER_SPEED, gripper_tgt)
        elif gripper_pwm > gripper_tgt:
            gripper_pwm = max(gripper_pwm - GRIPPER_SPEED, gripper_tgt)
        
        if gripper_pwm != last_gripper_pwm:
            gripper.value = gripper_pwm
            with state_lock:
                state["gripper_pwm"] = gripper_pwm
        
        time.sleep(0.02)

# --- BACKGROUND NETWORK DUAL VIDEO SERVER PROCESS ---
def video_server_worker():
    print("[Video Core] Initializing dual camera pipeline...")
    cap1 = cv2.VideoCapture(CAM_INDEX_1, cv2.CAP_V4L2)
    cap2 = cv2.VideoCapture(CAM_INDEX_2, cv2.CAP_V4L2)
    
    if not cap1.isOpened() or not cap2.isOpened():
        print(f"[Video Core Error] Failed to open one or both cameras (Index {CAM_INDEX_1} / {CAM_INDEX_2}).")
        if cap1.isOpened(): cap1.release()
        if cap2.isOpened(): cap2.release()
        return

    for cap in [cap1, cap2]:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    v_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    v_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    v_server.bind(("0.0.0.0", 5001))
    v_server.listen(1)
    
    print("[Video Core] Server open on Port 5001. Awaiting stream handshake...")
    try:
        v_conn, v_addr = v_server.accept()
        print(f"[Video Core] Stream tunnel linked to laptop client: {v_addr[0]}")
        while True:
            # Sync grab for both cameras
            cap1.grab()
            cap2.grab()
            
            ret1, frame1 = cap1.retrieve()
            ret2, frame2 = cap2.retrieve()
            
            if ret1 and ret2 and frame1 is not None and frame2 is not None:
                # Stitch frames side by side (Horizontal concatenation)
                # Resulting image will be 2560 x 720
                combined_frame = np.hstack((frame1, frame2))
                
                ret_enc, encoded_img = cv2.imencode('.jpg', combined_frame, [cv2.IMWRITE_JPEG_QUALITY, 55])
                if ret_enc:
                    frame_bytes = encoded_img.tobytes()
                    v_conn.sendall(len(frame_bytes).to_bytes(4, byteorder='big') + frame_bytes)
            else:
                time.sleep(0.01)
    except:
        pass
    finally:
        try: v_conn.close()
        except: pass
        v_server.close()
        cap1.release()
        cap2.release()
        print("[Video Core] Camera subsystem down cleanly.")

# --- NETWORK CONTROL COMMAND INTERFACE ---
def network_thread():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", 5000))
    server.listen(1)
    print("Control Server open on Port 5000. Waiting for laptop...")
    conn, addr = server.accept()
    print(f"Control channel active connected to: {addr}")

    buffer = ""
    V_SMOOTH_FACTOR = 0.20

    try:
        while True:
            with state_lock:
                if not state["running"]:
                    break

            data = conn.recv(1024).decode()
            if not data:
                with state_lock: state["running"] = False
                break
                
            with state_lock: state["last_heartbeat"] = time.time()  
                
            buffer += data
            if '\n' in buffer:
                lines = buffer.split('\n')
                buffer = lines.pop()
                msg = lines[-1].strip().split(',')
                if len(msg) < 18: continue

                if msg[BTN_DISCON_IDX] == "1":
                    with state_lock: state["running"] = False
                    break

                forward = msg[1] == "1"
                backward = msg[2] == "1"
                turn_left = msg[3] == "1"
                turn_right = msg[4] == "1"

                lf_pwm = NEUTRAL
                rf_pwm = NEUTRAL
                lr_pwm = NEUTRAL
                rr_pwm = NEUTRAL

                MOVE_POWER = 0.22
                TURN_POWER = 0.22

                if forward:
                    lf_pwm += MOVE_POWER; rf_pwm += MOVE_POWER; lr_pwm += MOVE_POWER; rr_pwm += MOVE_POWER
                elif backward:
                    lf_pwm -= MOVE_POWER; rf_pwm -= MOVE_POWER; lr_pwm -= MOVE_POWER; rr_pwm -= MOVE_POWER
                elif turn_left:
                    lf_pwm += TURN_POWER; rf_pwm += TURN_POWER; lr_pwm -= TURN_POWER; rr_pwm -= TURN_POWER
                elif turn_right:
                    lf_pwm -= TURN_POWER; rf_pwm -= TURN_POWER; lr_pwm += TURN_POWER; rr_pwm += TURN_POWER

                target_v = NEUTRAL
                if msg[BTN_ASCEND_IDX] == "1": target_v = ASCEND_PWM
                elif msg[BTN_DESCEND_IDX] == "1": target_v = DESCEND_PWM

                gripper_target = None
                if msg[KEY_A_IDX] == "1": gripper_target = GRIPPER_MAX
                elif msg[KEY_D_IDX] == "1": gripper_target = GRIPPER_MIN

                with state_lock:
                    state["h_pwms"] = [lf_pwm, rf_pwm, lr_pwm, rr_pwm]
                    state["v_base"] += (target_v - state["v_base"]) * V_SMOOTH_FACTOR
                    if gripper_target is not None:
                        state["gripper_target_pwm"] = gripper_target
    except Exception as e:
        print(f"Control link warning: {e}")
        with state_lock: state["running"] = False
    finally:
        conn.close()

if __name__ == "__main__":
    for i in range(16): set_pwm(i, NEUTRAL)
    print("ESC arming routine...")
    time.sleep(2)
    print("System armed and online.")

    vid_thread = threading.Thread(target=video_server_worker, daemon=True)
    vid_thread.start()

    motor_thread = threading.Thread(target=motor_control_thread, daemon=True)
    motor_thread.start()
    
    network_thread()

    print("Emergency shutdown initiated. Zeroing thrusters...")
    with state_lock:
        state["running"] = False
    time.sleep(0.1)
    
    for i in range(16): 
        try: pca.channels[i].duty_cycle = 0
        except: pass
        
    try:
        gripper.value = None
    except:
        pass
        
    print("ROV Core Safely Disengaged.")