import socket
import threading
import time
import os
import sys
import board
import busio
from adafruit_pca9685 import PCA9685
import numpy as np

# Disable GStreamer logging to prevent stdout cluttering
os.environ["OPENCV_VIDEOIO_PRIORITY_GSTREAMER"] = "0"
import cv2

# --- Linear Control Matrix & Limits ---
NEUTRAL = 1.6      
PWM_RANGE = 0.2    
PWM_MAX = NEUTRAL + PWM_RANGE
PWM_MIN = NEUTRAL - PWM_RANGE

# PCA9685 Channel Mapping
H_MOT_LF = 0; H_MOT_RF = 1; H_MOT_LR = 2; H_MOT_RR = 3
V_MOT_LF = 7; V_MOT_RF = 4; V_MOT_LR = 6; V_MOT_RR = 5

GRIPPER_CH = 8  
GRIP_MIN_MS = 0.55    
GRIP_MAX_MS = 2.45    
GRIP_SPEED_MS = 0.08  

# Controller Protocol Protocol Mapping Indices
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
    "gripper_ms": 1.5,  
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

    while True:
        with state_lock:
            if not state["running"]:
                break
            # Failsafe Timeout: Neutralize thrusters if link drops for > 1.2s
            if time.time() - state["last_heartbeat"] > 1.2:
                state["h_pwms"] = [NEUTRAL] * 4
                state["v_target"] = NEUTRAL
        
        with state_lock:
            state["v_curr"] += (state["v_target"] - state["v_curr"]) * V_SMOOTH_FACTOR
            v_base = state["v_curr"]
            h_pwms = state["h_pwms"].copy()
            current_gripper_ms = state["gripper_ms"]
            
        # Execute PWM Updates to PCA9685 Hardware Channels
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

# --- Ultra-Low Latency UDP Video Stream Worker with Anti-Explosion Strategy ---
def single_camera_stream_worker(video_device_index, port, cam_name, target_laptop_ip):
    cap = cv2.VideoCapture(video_device_index, cv2.CAP_V4L2)
    
    # Force Linux kernel V4L2 driver buffer size to 1 frame to kill backlog delay
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    
    # Optimization Strategy: Hybrid Resolutions configuration to drop network payload
    if cam_name == "CAM_MAIN":
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 20)
        pacing = 0.05
    else:
        # Scale secondary tracking feeds down to 320x240 (Cuts pixel data bandwidth by 75%)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        cap.set(cv2.CAP_PROP_FPS, 10)
        pacing = 0.10
        
    # UDP Initialization: Fire packets continuously without waiting for handshake checks
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dest_address = (target_laptop_ip, port)
    
    try:
        dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(dummy_frame, f"{cam_name} OFFLINE", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        while True:
            with state_lock:
                if not state["running"]: 
                    break
                
            ret, frame = (cap.read() if (cap and cap.isOpened()) else (False, None))
            final_frame = frame if (ret and frame is not None) else dummy_frame
            
            # Compress with an optimized Quality factor (20) to shrink frame weight dramatically
            ret_enc, encoded_img = cv2.imencode('.jpg', final_frame, [cv2.IMWRITE_JPEG_QUALITY, 20])
            if ret_enc:
                frame_bytes = encoded_img.tobytes()
                
                # CRITICAL FAILSAFE: Strict threshold to eliminate [Errno 90] Message too long
                SAFE_UDP_CEILING = 50000 
                
                if len(frame_bytes) < SAFE_UDP_CEILING:
                    try:
                        udp_sock.sendto(frame_bytes, dest_address)
                    except socket.error:
                        # Silently swallow socket pipeline spikes without killing thread loop
                        pass
                else:
                    # Emergency Downscaling Action: Shrink resolution dynamically if image data overflows MTU
                    shrunk_frame = cv2.resize(final_frame, (final_frame.shape[1] // 2, final_frame.shape[0] // 2))
                    ret_enc_low, encoded_img_low = cv2.imencode('.jpg', shrunk_frame, [cv2.IMWRITE_JPEG_QUALITY, 15])
                    if ret_enc_low:
                        try:
                            udp_sock.sendto(encoded_img_low.tobytes(), dest_address)
                        except:
                            pass
                        
            time.sleep(pacing)
                
    except Exception as e:
        print(f"[{cam_name} Exception] Stream Worker error: {e}")
    finally:
        try:
            udp_sock.close()
        except:
            pass
        if cap and cap.isOpened(): 
            cap.release()
        print(f"[{cam_name}] Video hardware channel stream released safely.")

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
        
        # Dynamically harvest laptop IP from telemetry channel to feed UDP pipes
        laptop_ip = addr[0]
        
        # === DYNAMIC CAMERA SCANNING ENGINE ===
        # Automates validation of valid /dev/videoX capture nodes on current system state
        available_cams = []
        for i in range(16):
            if os.path.exists(f"/dev/video{i}"):
                cap_test = cv2.VideoCapture(i, cv2.CAP_V4L2)
                if cap_test.isOpened():
                    available_cams.append(i)
                    cap_test.release()
                if len(available_cams) >= 3:
                    break
        
        # Fallback allocation logic to prevent runtime thread instantiation collapse
        while len(available_cams) < 3:
            fallback = len(available_cams) * 4
            available_cams.append(fallback)
            
        print(f"[Auto Scanner] Active valid V4L2 device indexes routed: {available_cams}")
        
        # Deploy streaming worker threads using discovered hardware nodes
        threading.Thread(target=single_camera_stream_worker, args=(available_cams[0], 5001, "CAM_MAIN", laptop_ip), daemon=True).start()
        threading.Thread(target=single_camera_stream_worker, args=(available_cams[1], 5002, "CAM_BOTTOM", laptop_ip), daemon=True).start()
        threading.Thread(target=single_camera_stream_worker, args=(available_cams[2], 5003, "CAM_AUX", laptop_ip), daemon=True).start()
        # ======================================

        buffer = ""
        while True:
            with state_lock:
                if not state["running"]: 
                    break

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
                    if len(msg) < 18: 
                        continue

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
                    lf_mix = joy_y + joy_x
                    rf_mix = joy_y - joy_x
                    lr_mix = joy_y - joy_x
                    rr_mix = joy_y + joy_x

                    max_val = max(abs(lf_mix), abs(rf_mix), abs(lr_mix), abs(rr_mix), 1.0)
                    lf_pwm = NEUTRAL + (lf_mix / max_val) * PWM_RANGE
                    rf_pwm = NEUTRAL + (rf_mix / max_val) * PWM_RANGE
                    lr_pwm = NEUTRAL + (lr_mix / max_val) * PWM_RANGE
                    rr_pwm = NEUTRAL + (rr_mix / max_val) * PWM_RANGE

                    target_v = NEUTRAL + (joy_v * PWM_RANGE)

                    servo_change = 0.0
                    if msg[KEY_A_IDX] == "1":   
                        servo_change = GRIP_SPEED_MS
                    elif msg[KEY_D_IDX] == "1": 
                        servo_change = -GRIP_SPEED_MS

                    with state_lock:
                        state["h_pwms"] = [lf_pwm, rf_pwm, lr_pwm, rr_pwm]
                        state["v_target"] = target_v
                        
                        new_ms = state["gripper_ms"] + servo_change
                        state["gripper_ms"] = max(min(new_ms, GRIP_MAX_MS), GRIP_MIN_MS)
                        
    except Exception as e:
        print(f"[Control Link Error] Exception forced shutdown: {e}")
        with state_lock: state["running"] = False
    finally:
        try: conn.close()
        except: pass
        server.close()

# --- Execution Runtime Initialization Entrypoint ---
if __name__ == "__main__":
    print("[Failsafe System] Initializing channels to absolute neutral...")
    for i in range(16): 
        set_pwm(i, NEUTRAL)
    print("[Failsafe System] ESC lock arming, please hold still for 2 seconds...")
    time.sleep(2)
    print("[Failsafe System] Core engine online.")

    # Launch core control & parsing sub-threads
    threading.Thread(target=motor_control_thread, daemon=True).start()
    threading.Thread(target=network_thread, daemon=True).start()

    try:
        while True:
            with state_lock:
                if not state["running"]: 
                    break
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[Manual Interruption] Keyboard interrupt caught on Pi Core.")

    # Safe Shutdown Clean Routine: Neutralize All Hardware Channels immediately
    with state_lock: 
        state["running"] = False
    for i in range(8): 
        try: set_pwm(i, NEUTRAL)
        except: pass
    time.sleep(1.0)
    for i in range(8, 16): 
        if i == GRIPPER_CH: 
            continue
        try: pca.channels[i].duty_cycle = 0
        except: pass
    print("[Emergency Shutdown] ROV Core safely neutralized. Goodbye.")