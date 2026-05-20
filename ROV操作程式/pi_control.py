import socket
import threading
import time
import math
import board
import busio
from adafruit_pca9685 import PCA9685
import adafruit_bno055

# 全域變數區
NEUTRAL = 1.65
PWM_MAX = 2.1
PWM_MIN = 1.1
MAX_THRUST = 0.25

ASCEND_PWM = 1.8
DESCEND_PWM = 1.5

# 夾爪 (Servo) 設定
GRIPPER_CH = 8
GRIPPER_MAX = 2.5  # 夾爪全開的 PWM 值
GRIPPER_MIN = 0.5  # 夾爪全關的 PWM 值
GRIPPER_SPEED = 0.08 

# 垂直馬達硬體通道定義
V_MOT_LF = 7  
V_MOT_RF = 4  
V_MOT_LR = 6  
V_MOT_RR = 5  

# 通訊陣列索引定義
JOY_LX_IDX = 1
JOY_LY_IDX = 2
JOY_RX_IDX = 3
JOY_RY_IDX = 4
KEY_A_IDX = 5       # 夾爪開到底
KEY_D_IDX = 6       # 夾爪關到底
BTN_RESET_IDX = 7   # 一鍵朝前重置
BTN_AUTO_RET_IDX = 8 # 自動返航標記
BTN_ASCEND_IDX = 15 # 垂直上升
BTN_DESCEND_IDX = 16# 垂直下降
BTN_DISCON_IDX = 17 # 控制端中斷連線訊號
JOY_DEADZONE = 0.1

# 姿態與定航設定
Kp_v = 0.007
Kp_h = 0.005

TILT_LIMIT = 15.0
PITCH_LIMIT = 30.0
PAN_LIMIT = 90.0

YAW_DEADZONE = 1.5
YAW_MAX_COMP = 0.12


# 狀態與執行緒鎖
state_lock = threading.Lock() # 避免讀寫衝突的執行緒鎖
state = {
    "h_pwms": [NEUTRAL] * 4,
    "v_base": NEUTRAL,
    "target_pitch": 0.0,
    "target_roll": 0.0,
    "target_yaw": 0.0,
    "base_yaw": 0.0,
    "base_pitch": 0.0,  
    "base_roll": 0.0,   
    "is_turning": False,
    "running": True,
    
    # 夾爪開機預設改為「閉合 (MIN)」，防止瞬間大電流抽載 (Brownout)
    "gripper_target_pwm": GRIPPER_MIN, 
    "gripper_pwm": GRIPPER_MIN,        
    
    # 容錯處理 (Fail-Safe) 專用變數
    "last_heartbeat": time.time(),         # 網路看門狗時間戳記
    "last_valid_sensor": (0.0, 0.0, 0.0)   # IMU 當機備援資料 (Pitch, Roll, Yaw)
}


# 硬體初始化
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    pca = PCA9685(i2c)
    pca.frequency = 50
    
    bno = adafruit_bno055.BNO055_I2C(i2c)

    print("Hardware initialized: PCA9685, BNO055 OK.")
except Exception as e:
    print(f"Init failed: {e}")
    exit()

def update_sensors():
    try:
        yaw, roll, pitch = bno.euler
        if yaw is None or roll is None or pitch is None:
            raise ValueError("Sensor returned None")
        
        pitch = max(min(pitch, 85.0), -85.0)
        roll = max(min(roll, 85.0), -85.0)
        
        with state_lock:
            state["last_valid_sensor"] = (pitch, roll, yaw)
            
        return pitch, roll, yaw
    except Exception as e:
        with state_lock:
            return state["last_valid_sensor"]

def set_pwm(ch, ms):
    if ch == GRIPPER_CH:
        ms = max(min(ms, GRIPPER_MAX), GRIPPER_MIN)
    else:
        ms = max(min(ms, PWM_MAX), PWM_MIN)
        
    duty = int((ms / 20.0) * 65535)
    pca.channels[ch].duty_cycle = duty

def motor_control_thread():
    print("Control engine started")
    while state["running"]:
        
        with state_lock:
            if time.time() - state["last_heartbeat"] > 1.5:
                state["h_pwms"] = [NEUTRAL] * 4
                state["v_base"] = NEUTRAL
        
        with state_lock:
            target_p = state["target_pitch"]
            target_r = state["target_roll"]
            target_y = state["target_yaw"]
            v_base = state["v_base"]
            h_pwms = state["h_pwms"].copy()
            is_turning = state["is_turning"]
            gripper_tgt = state["gripper_target_pwm"]
            gripper_pwm = state["gripper_pwm"]
            
        cp, cr, cy = update_sensors()
        
        p_comp = (cp - target_p) * Kp_v
        r_comp = (cr - target_r) * Kp_v
        
        y_error = cy - target_y
        y_error = (y_error + 180) % 360 - 180

        y_comp = 0
        if not is_turning:
            if abs(y_error) > YAW_DEADZONE:
                y_comp = y_error * Kp_h
                y_comp = max(min(y_comp, YAW_MAX_COMP), -YAW_MAX_COMP)

        # ==========================================
        # 垂直控制 Mixer (已修正)
        # 注意：如果您測試時，推「點頭」還是發生「左右側翻」的動作，
        # 請將下面算式裡的 p_comp 跟 r_comp 交換位置 (因為這代表您的 IMU 轉了 90 度)。
        # ==========================================
        set_pwm(V_MOT_LF, v_base - p_comp + r_comp)
        set_pwm(V_MOT_RF, v_base - p_comp - r_comp)
        set_pwm(V_MOT_LR, v_base + p_comp + r_comp)
        set_pwm(V_MOT_RR, v_base + p_comp - r_comp)
        
        # ==========================================
        # 水平控制 Mixer (已修正重大 Bug)
        # Yaw 轉向應為「左邊馬達 vs 右邊馬達」的差動，而非前後。
        # ==========================================
        set_pwm(0, h_pwms[0] + y_comp) # LF (左前)
        set_pwm(1, h_pwms[1] - y_comp) # RF (右前)
        set_pwm(2, h_pwms[2] + y_comp) # LR (左後)
        set_pwm(3, h_pwms[3] - y_comp) # RR (右後)
        
        # 夾爪邏輯
        last_gripper_pwm = gripper_pwm
        if gripper_pwm < gripper_tgt:
            gripper_pwm = min(gripper_pwm + GRIPPER_SPEED, gripper_tgt)
        elif gripper_pwm > gripper_tgt:
            gripper_pwm = max(gripper_pwm - GRIPPER_SPEED, gripper_tgt)
        
        if gripper_pwm != last_gripper_pwm:
            set_pwm(GRIPPER_CH, gripper_pwm)
            with state_lock:
                state["gripper_pwm"] = gripper_pwm
        
        time.sleep(0.02)

def network_thread():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", 5000))
    server.listen(1)
    print("Waiting for connection...")
    conn, addr = server.accept()
    print(f"Connected: {addr}")

    buffer = ""
    smooth_pitch = state["base_pitch"] 
    PITCH_SMOOTH_FACTOR = 0.05
    V_SMOOTH_FACTOR = 0.08

    try:
        while state["running"]:
            data = conn.recv(1024).decode()
            if not data:
                print("警告：控制端連線中斷！")
                state["running"] = False
                break
                
            with state_lock:
                state["last_heartbeat"] = time.time()  
                
            buffer += data
            if '\n' in buffer:
                lines = buffer.split('\n')
                buffer = lines.pop()
                msg = lines[-1].strip().split(',')
                if len(msg) < 18: continue

                if msg[BTN_DISCON_IDX] == "1":
                    state["running"] = False
                    break

                is_auto_returning = False
                try:
                    joy_lx = float(msg[JOY_LX_IDX])
                    joy_ly = float(msg[JOY_LY_IDX])
                    joy_rx = float(msg[JOY_RX_IDX])
                    joy_ry = float(msg[JOY_RY_IDX])
                    if len(msg) > 8 and msg[BTN_AUTO_RET_IDX] == "1":
                        is_auto_returning = True
                except ValueError:
                    continue

                if abs(joy_lx) < JOY_DEADZONE: joy_lx = 0.0
                if abs(joy_ly) < JOY_DEADZONE: joy_ly = 0.0
                if abs(joy_rx) < JOY_DEADZONE: joy_rx = 0.0
                if abs(joy_ry) < JOY_DEADZONE: joy_ry = 0.0

                with state_lock:
                    if msg[BTN_RESET_IDX] == "1":
                        current_p, current_r, current_y = update_sensors()
                        state["base_yaw"] = current_y
                        state["target_yaw"] = current_y
                        state["base_pitch"] = current_p
                        state["base_roll"] = current_r
                        state["target_pitch"] = current_p
                        state["target_roll"] = current_r
                        print(f"基準已重置: Yaw={current_y:.1f}°, Pitch={current_p:.1f}°, Roll={current_r:.1f}°")

                    if is_auto_returning:
                        joy_lx = 0.0
                        turning = False
                    else:
                        turning = abs(joy_lx) > 0.0

                    if state["is_turning"] and not turning:
                        _, _, current_y = update_sensors()
                        state["base_yaw"] = current_y
                    state["is_turning"] = turning

                    if not turning:
                        target_y_offset = state["base_yaw"] - (joy_rx * PAN_LIMIT)
                        state["target_yaw"] = (target_y_offset + 360) % 360

                    thrust_y = joy_ly * MAX_THRUST
                    thrust_x = joy_lx * MAX_THRUST
                    left_thrust = max(min(thrust_y + thrust_x, MAX_THRUST), -MAX_THRUST)
                    right_thrust = max(min(thrust_y - thrust_x, MAX_THRUST), -MAX_THRUST)

                    # ==========================================
                    # 水平推力陣列配置
                    # 原本錯把左右推力分配成前後，現在正確分配給左側與右側馬達
                    # ==========================================
                    state["h_pwms"] = [
                        NEUTRAL + left_thrust,   # 0: H_LF (左側)
                        NEUTRAL + right_thrust,  # 1: H_RF (右側)
                        NEUTRAL + left_thrust,   # 2: H_LR (左側)
                        NEUTRAL + right_thrust   # 3: H_RR (右側)
                    ]

                    raw_pitch = state["base_pitch"] - (TILT_LIMIT * joy_ly) - (PITCH_LIMIT * joy_ry)
                    smooth_pitch += (raw_pitch - smooth_pitch) * PITCH_SMOOTH_FACTOR
                    max_p = state["base_pitch"] + PITCH_LIMIT
                    min_p = state["base_pitch"] - PITCH_LIMIT
                    state["target_pitch"] = max(min(smooth_pitch, max_p), min_p)

                    if msg[BTN_ASCEND_IDX] == "1":
                        target_v = ASCEND_PWM
                    elif msg[BTN_DESCEND_IDX] == "1":
                        target_v = DESCEND_PWM
                    else:
                        target_v = NEUTRAL

                    state["v_base"] += (target_v - state["v_base"]) * V_SMOOTH_FACTOR
                    
                    if msg[KEY_A_IDX] == "1":
                        state["gripper_target_pwm"] = GRIPPER_MAX
                    elif msg[KEY_D_IDX] == "1":
                        state["gripper_target_pwm"] = GRIPPER_MIN

    except Exception as e:
        print(f"網路執行緒發生錯誤: {e}")
        state["running"] = False
    finally:
        conn.close()

if __name__ == "__main__":
    for i in range(9): set_pwm(i, NEUTRAL)
    print("ESC & Gripper unlocking...")
    time.sleep(2)

    ENABLE_MOTOR_TEST = False  # 測試完畢確認無誤後，請將此處改為 False 關閉測試
    
    if ENABLE_MOTOR_TEST:
        print("\n--- 開始馬達順序校正測試 ---")
        TEST_THRUST = NEUTRAL + 0.08  
        
        motor_test_list = [
            (0, "水平-左前 (H_LF, PIN 0)"),
            (1, "水平-右前 (H_RF, PIN 1)"),
            (2, "水平-左後 (H_LR, PIN 2)"),
            (3, "水平-右後 (H_RR, PIN 3)"),
            (V_MOT_LF, f"垂直-左前 (V_MOT_LF, PIN {V_MOT_LF})"),
            (V_MOT_RF, f"垂直-右前 (V_MOT_RF, PIN {V_MOT_RF})"),
            (V_MOT_LR, f"垂直-左後 (V_MOT_LR, PIN {V_MOT_LR})"),
            (V_MOT_RR, f"垂直-右後 (V_MOT_RR, PIN {V_MOT_RR})")
        ]

        for ch, name in motor_test_list:
            print(f"👉 正在轉動: {name}")
            set_pwm(ch, TEST_THRUST)  
            time.sleep(1.5)           
            set_pwm(ch, NEUTRAL)      
            time.sleep(0.5)           
            
        print("--- 馬達校正測試完畢 ---\n")

    print("Reading initial sensor states...")
    p_init, r_init, y_init = update_sensors()
    
    with state_lock:
        state["target_yaw"] = y_init
        state["base_yaw"] = y_init  
        state["target_pitch"] = p_init
        state["base_pitch"] = p_init
        state["target_roll"] = r_init
        state["base_roll"] = r_init

    print(f"Ready. Initial Yaw={y_init:.1f}°, Pitch={p_init:.1f}°, Roll={r_init:.1f}°")

    threading.Thread(target=motor_control_thread, daemon=True).start()
    network_thread()

    print("Zeroing all motors before exit...")
    for i in range(9): set_pwm(i, NEUTRAL)
    print("System stopped safely.")