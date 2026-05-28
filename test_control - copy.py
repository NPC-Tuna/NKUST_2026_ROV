import socket
import pygame
import time
import sys
import cv2
import numpy as np
import threading

HOST = "192.168.0.141"
CTRL_PORT = 5000
VIDEO_PORT = 5001

# Global image buffer for background video receiver thread
shared_frame_data = {"main_frame": None, "running": True}

def video_receiver_thread():
    print("[Video Link] Initializing background network sync...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, VIDEO_PORT))
        print("[Video Link] Connected to Pi 5 dual-camera streaming pipeline.")
    except Exception as e:
        print(f"[Video Link Error] Connection refused: {e}")
        shared_frame_data["running"] = False
        return

    data_buffer = b""
    while shared_frame_data["running"]:
        try:
            while len(data_buffer) < 4:
                packet = sock.recv(4096)
                if not packet:
                    raise RuntimeError("Bytes drop")
                data_buffer += packet
            
            packed_size = data_buffer[:4]
            msg_size = int.from_bytes(packed_size, byteorder='big')
            
            while len(data_buffer) < 4 + msg_size:
                packet = sock.recv(4096)
                if not packet:
                    raise RuntimeError("Bytes drop")
                data_buffer += packet
                
            img_data = data_buffer[4 : 4 + msg_size]
            data_buffer = data_buffer[4 + msg_size:]
            
            np_arr = np.frombuffer(img_data, dtype=np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                shared_frame_data["main_frame"] = frame
        except Exception as ex:
            print(f"[Video Link] Stream disconnected or error: {ex}")
            break
            
    sock.close()
    shared_frame_data["running"] = False

def main():
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("[Error] Xbox controller not detected! Check USB/Bluetooth link.")
        sys.exit()

    joystick = pygame.joystick.Joystick(0)
    joystick.init()

    # 調整視窗為更寬的比例，容納雙水下鏡頭並排
    WIDTH, HEIGHT = 1200, 500  
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("NKUST ROV OVERSEER DUAL-CAM CONTROL SYSTEM")

    # Local Laptop Sub Camera (0 = Built-in webcam)
    cap_sub = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((HOST, CTRL_PORT))
        print("[Control Link] Connected to Raspberry Pi 5 Motor Core.")
    except Exception as e:
        print("[Control Link Error] Connection failed:", e)
        sys.exit()

    v_thread = threading.Thread(target=video_receiver_thread, daemon=True)
    v_thread.start()

    running = True
    DEADZONE = 0.3
    clock = pygame.time.Clock()

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # --- Read Controls ---
        try:
            joy_x = joystick.get_axis(0)
            joy_y = joystick.get_axis(1)
        except:
            joy_x, joy_y = 0.0, 0.0

        btn_lb = joystick.get_button(4)
        btn_rb = joystick.get_button(5)
        
        try:
            trigger_lt = joystick.get_axis(4) 
            trigger_rt = joystick.get_axis(5)
        except:
            trigger_lt, trigger_rt = -1.0, -1.0

        keys = pygame.key.get_pressed()
        msg = ["0"] * 18

        if keys[pygame.K_ESCAPE]:
            msg[17] = "1"
            running = False

        # --- Motion Mapping Logic ---
        if joy_y < -DEADZONE:
            msg[1] = "1"  
        elif joy_y > DEADZONE:
            msg[2] = "1"  

        if joy_x < -DEADZONE:
            msg[3] = "1"  
        elif joy_x > DEADZONE:
            msg[4] = "1"  

        if btn_lb:
            msg[15] = "1" 
        if btn_rb:
            msg[16] = "1" 

        if trigger_lt > -0.5 or keys[pygame.K_a]:
            msg[5] = "1"  

        if trigger_rt > -0.5 or keys[pygame.K_d]:
            msg[6] = "1"  

        # --- Packet Dispatcher ---
        data_str = ",".join(msg)
        try:
            client.sendall((data_str + "\n").encode())
        except:
            print("[Control Link] Transmission failure.")
            running = False

        # ========================================================
        # UI Rendering Engine (Split Dual-Cam Blitting)
        # ========================================================
        combined_frame = shared_frame_data["main_frame"]

        if combined_frame is not None:
            # 這裡把 2560x720 的大圖從中間左右對半切
            h, w, _ = combined_frame.shape
            mid_x = w // 2
            frame_cam1 = combined_frame[:, :mid_x]  # 左半邊：相機 1
            frame_cam2 = combined_frame[:, mid_x:]  # 右半邊：相機 2

            # 計算單個相機畫面在 Pygame 視窗中的分配尺寸
            cam_w = WIDTH // 2
            cam_h = HEIGHT

            # 渲染左邊鏡頭 (Camera 1)
            frame_cam1 = cv2.cvtColor(frame_cam1, cv2.COLOR_BGR2RGB)
            frame_cam1 = cv2.resize(frame_cam1, (cam_w, cam_h))
            surf_cam1 = pygame.image.frombuffer(frame_cam1.tobytes(), (cam_w, cam_h), "RGB")
            screen.blit(surf_cam1, (0, 0))

            # 渲染右邊鏡頭 (Camera 2)
            frame_cam2 = cv2.cvtColor(frame_cam2, cv2.COLOR_BGR2RGB)
            frame_cam2 = cv2.resize(frame_cam2, (cam_w, cam_h))
            surf_cam2 = pygame.image.frombuffer(frame_cam2.tobytes(), (cam_w, cam_h), "RGB")
            screen.blit(surf_cam2, (cam_w, 0))
            
            # 在畫面中央畫一條細分隔線
            pygame.draw.line(screen, (50, 50, 50), (cam_w, 0), (cam_w, HEIGHT), 2)
        else:
            screen.fill((20, 20, 20))
            if not shared_frame_data["running"]:
                font = pygame.font.SysFont(None, 36)
                text = font.render("VIDEO STREAM DISCONNECTED - CONTROL ACTIVE", True, (255, 50, 50))
                screen.blit(text, (20, HEIGHT - 40))

        # Render Laptop Local Sub Camera (PiP Display Layer in corner)
        ret_sub, frame_sub = cap_sub.read()
        if ret_sub:
            frame_sub = cv2.cvtColor(frame_sub, cv2.COLOR_BGR2RGB)
            pip_w, pip_h = 160, 90  # 稍微縮小筆電鏡頭以利觀察水下
            frame_sub = cv2.resize(frame_sub, (pip_w, pip_h))
            pip_surface = pygame.image.frombuffer(frame_sub.tobytes(), (pip_w, pip_h), "RGB")
            screen.blit(pip_surface, (WIDTH - pip_w - 10, 10))

        pygame.display.flip()
        clock.tick(30)

    # Clean Exit Handshake
    shared_frame_data["running"] = False
    msg = ["0"] * 18
    msg[17] = "1"
    try:
        client.sendall(((",".join(msg)) + "\n").encode())
    except:
        pass

    client.close()
    cap_sub.release()
    pygame.quit()
    print("Laptop station shut down clean.")

if __name__ == "__main__":
    main()