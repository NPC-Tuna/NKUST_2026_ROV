'''

sudo systemctl list-units --type=service --all | grep -E -i "video|stream|web|camera|rov|abyss|capture|picam|mjpg|live"

sudo systemctl stop abyss_cam.service

sudo systemctl disable abyss_cam.service

'''

import socket

import threading

import time

import os

import sys

import board

import busio

from adafruit_pca9685 import PCA9685

import numpy as np

import math

import time



os.environ["OPENCV_VIDEOIO_PRIORITY_GSTREAMER"] = "0"

import cv2



# --- Linear Control Matrix & Limits ---

NEUTRAL = 1.6      

PWM_RANGE = 0.25    

PWM_MAX = NEUTRAL + PWM_RANGE

PWM_MIN = NEUTRAL - PWM_RANGE



# PCA9685 Channel Mapping

H_MOT_LF = 0; H_MOT_RF = 1; H_MOT_LR = 2; H_MOT_RR = 3

V_MOT_LF = 7; V_MOT_RF = 4; V_MOT_LR = 6; V_MOT_RR = 5



GRIPPER_CH = 8

GRIP_MIN_MS = 0.45

GRIP_MAX_MS = 2.45



GRIP_MARGIN_MS = 0.15   # safety margin at both ends, avoids stalling against the mechanical stop (lower it if grip is too weak)                                 

GRIP_RATE_MS = 1.0      # pulse-width moved per second while held (open/close speed; larger = faster)

GRIP_OPEN_POS = 1.50




GRIP_CLOSE_POS = 0.45
GRIP_DEFAULT_MS = GRIP_CLOSE_POS               # power-on default position = closed                               

# Positional servo: moves only while held, stays at current angle on release and holds grip with servo torque         

# GRIP_MIN_MS / GRIP_MAX_MS remain as the final hard safety range inside set_pwm 



# Controller Protocol Mapping Indices

JOY_X_IDX = 1       

JOY_Y_IDX = 2       

JOY_V_IDX = 3       

KEY_A_IDX = 5         

KEY_D_IDX = 6       

BTN_DISCON_IDX = 17



# Thread Isolation Structures

state_lock = threading.Lock() 

state = {

    "h_pwms": [NEUTRAL] * 4,

    "v_target": NEUTRAL,      

    "v_curr": NEUTRAL,

    "gripper_ms": GRIP_DEFAULT_MS,   # power-on default = closed

    "gripper_dir": 0,                # 1=closing, -1=opening, 0=hold current angle

    "running": True,

    "last_heartbeat": time.time()       

}



# --- Hardware Initialization ---

try:

    i2c = busio.I2C(board.SCL, board.SDA)

    pca = PCA9685(i2c)

    pca.frequency = 50

    print("[Hardware Success] PCA9685 I2C communication established.")

except Exception as e:

    print(f"[Hardware Failure] PCA9685 initialization failed: {e}")

    sys.exit()



def set_pwm(ch, ms):

    ms = max(min(ms, GRIP_MAX_MS if ch == GRIPPER_CH else PWM_MAX), GRIP_MIN_MS if ch == GRIPPER_CH else PWM_MIN)

    duty = int((ms / 20.0) * 65535)

    pca.channels[ch].duty_cycle = duty



# --- Actuator Control Loop Thread ---

def motor_control_thread():

    print("[Control Engine] Linear thruster hardware control engine active.")

    V_SMOOTH_FACTOR = 0.15

    last_time = time.time()



    while True:

        now = time.time()

        dt = now - last_time

        last_time = now



        with state_lock:

            if not state["running"]:

                break

            if time.time() - state["last_heartbeat"] > 1.2:

                state["h_pwms"] = [NEUTRAL] * 4

                state["v_target"] = NEUTRAL

                state["gripper_dir"] = 0   # link lost: stop gripper movement, hold current angle to keep grip



        with state_lock:

            state["v_curr"] += (state["v_target"] - state["v_curr"]) * V_SMOOTH_FACTOR

            v_base = state["v_curr"]

            h_pwms = state["h_pwms"].copy()



            # Gripper positional rate control: move while held, hold on release, clamped within soft limits (never hits mechanical stop)

            if state["gripper_dir"] != 0:

                state["gripper_ms"] += state["gripper_dir"] * GRIP_RATE_MS * dt

                state["gripper_ms"] = max(min(state["gripper_ms"], GRIP_OPEN_POS), GRIP_CLOSE_POS)

            current_gripper_ms = state["gripper_ms"]

            

        set_pwm(V_MOT_LF, v_base)

        set_pwm(V_MOT_RF, v_base)

        set_pwm(V_MOT_LR, v_base)

        set_pwm(V_MOT_RR, v_base)

        

        set_pwm(H_MOT_LF, h_pwms[0]) 

        set_pwm(H_MOT_RF, h_pwms[1]) 

        set_pwm(H_MOT_LR, h_pwms[2]) 

        set_pwm(H_MOT_RR, h_pwms[3]) 

        

        set_pwm(GRIPPER_CH, current_gripper_ms)

        time.sleep(0.02) 



# --- STABLE VERSION: Software Compressed Video Stream Engine ---

def single_camera_stream_worker(video_device_index, port, cam_name, target_laptop_ip):

    cap = cv2.VideoCapture(video_device_index, cv2.CAP_V4L2)

    

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  

    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    dest_address = (target_laptop_ip, port)

    

    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 40]

    print(f"[{cam_name}] Standard Optimized Engine Ready -> {target_laptop_ip}:{port}")

    

    try:

        while True:

            with state_lock:

                if not state["running"]: 

                    break

                

            ret, frame = cap.read()

            if ret and frame is not None:

                

                frame_resized = cv2.resize(frame, (480, 360))

                

                result, encimg = cv2.imencode('.jpg', frame_resized, encode_param)

                

                if result:

                    frame_bytes = encimg.tobytes()

                    frame_size = len(frame_bytes)

                    

                    if frame_size < 65000:

                        try:

                            udp_sock.sendto(frame_bytes, dest_address)

                        except socket.error:

                            pass

                    else:

                        print(f"[{cam_name} WARNING] Frame oversized ({frame_size} bytes), dropped.")

            else:

                time.sleep(0.01)

                

    except Exception as e:

        print(f"[{cam_name} Exception] Stream error: {e}")

    finally:

        try: udp_sock.close()

        except: pass

        if cap and cap.isOpened(): cap.release()

        print(f"[{cam_name}] Video hardware detached safely.")



# --- TCP Network Listener & Command Parsing Thread ---

def network_thread():

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server.bind(("0.0.0.0", 5000))

    server.listen(1)

    print("[Control Link] Port 5000 listening for Vector Commands...")

    

    try:

        conn, addr = server.accept()

        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        print(f"[Control Link] Linear session verified with client: {addr}")

        

        laptop_ip = addr[0]

        

        # === DYNAMIC CAMERA SCANNING ENGINE ===

        available_cams = []

        for i in range(16):

            if os.path.exists(f"/dev/video{i}"):

                cap_test = cv2.VideoCapture(i, cv2.CAP_V4L2)

                if cap_test.isOpened():

                    available_cams.append(i)

                    cap_test.release()

                if len(available_cams) >= 3:

                    break

        

        while len(available_cams) < 3:

            fallback = len(available_cams) * 4

            available_cams.append(fallback)

            

        print(f"[Auto Scanner] Active valid V4L2 device indexes routed: {available_cams}")

        

        threading.Thread(target=single_camera_stream_worker, args=(available_cams[0], 5001, "CAM_MAIN", laptop_ip), daemon=True).start()

        threading.Thread(target=single_camera_stream_worker, args=(available_cams[1], 5002, "CAM_BOTTOM", laptop_ip), daemon=True).start()

        threading.Thread(target=single_camera_stream_worker, args=(available_cams[2], 5003, "CAM_AUX", laptop_ip), daemon=True).start()



        buffer = ""

        while True:

            with state_lock:

                if not state["running"]: break



            data = conn.recv(1024).decode()

            if not data:

                with state_lock: state["running"] = False

                break

                

            with state_lock: 

                state["last_heartbeat"] = time.time()  

                

            buffer += data

            while '\n' in buffer:

                lines = buffer.split('\n')

                buffer = lines.pop()

                for line in lines:

                    msg = line.strip().split(',')

                    if len(msg) < 18: continue



                    if msg[BTN_DISCON_IDX] == "1":

                        with state_lock: state["running"] = False

                        break



                    try:

                        joy_x = float(msg[JOY_X_IDX])  

                        joy_y = float(msg[JOY_Y_IDX])  

                        joy_v = float(msg[JOY_V_IDX])  

                    except ValueError:

                        continue 



                    # Kinematic Mixing Matrix Calculations

                    lf_mix = joy_y - joy_x

                    rf_mix = joy_y - joy_x

                    lr_mix = joy_y + joy_x

                    rr_mix = joy_y + joy_x



                    max_val = max(abs(lf_mix), abs(rf_mix), abs(lr_mix), abs(rr_mix), 1.0)

                    lf_pwm = NEUTRAL + (lf_mix / max_val) * PWM_RANGE

                    rf_pwm = NEUTRAL + (rf_mix / max_val) * PWM_RANGE

                    lr_pwm = NEUTRAL + (lr_mix / max_val) * PWM_RANGE

                    rr_pwm = NEUTRAL + (rr_mix / max_val) * PWM_RANGE



                    target_v = NEUTRAL + (joy_v * PWM_RANGE)



                    with state_lock:

                        if msg[KEY_A_IDX] == "1":

                            state["gripper_dir"] = 1     # hold A: move toward closed

                        elif msg[KEY_D_IDX] == "1":

                            state["gripper_dir"] = -1    # hold D: move toward open

                        else:

                            state["gripper_dir"] = 0     # released: hold current angle



                        state["h_pwms"] = [lf_pwm, rf_pwm, lr_pwm, rr_pwm]

                        state["v_target"] = target_v

                        

    except Exception as e:

        print(f"[Control Link Error] Exception forced shutdown: {e}")

        with state_lock: state["running"] = False

    finally:

        try: conn.close()

        except: pass

        server.close()



if __name__ == "__main__":

    print("[Failsafe System] Initializing channels to absolute neutral...")

    for i in range(16): set_pwm(i, NEUTRAL)

    print("[Failsafe System] ESC lock arming, please hold still for 2 seconds...")

    time.sleep(2)



    # Power-on default closed: command the positional servo straight to the closed angle

    print("[Init] Setting gripper to default (closed) position...")

    set_pwm(GRIPPER_CH, GRIP_DEFAULT_MS)

    print("[Init] Gripper defaulted to closed.")



    print("[Failsafe System] Core engine online.")



    threading.Thread(target=motor_control_thread, daemon=True).start()

    threading.Thread(target=network_thread, daemon=True).start()



    try:

        while True:

            with state_lock:

                if not state["running"]: break

            time.sleep(0.1)

    except KeyboardInterrupt:

        print("\n[Manual Interruption] Keyboard interrupt caught on Pi Core.")



    with state_lock: state["running"] = False

    for i in range(8):

        try: set_pwm(i, NEUTRAL)

        except: pass

    time.sleep(1.0)

    for i in range(8, 16):

        if i == GRIPPER_CH: continue   # keep gripper at last angle (servo keeps holding grip), do not zero

        try: pca.channels[i].duty_cycle = 0

        except: pass

    print("[Emergency Shutdown] ROV Core safely neutralized. Goodbye.")

