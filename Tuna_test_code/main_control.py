import socket
import pygame
import time
import sys
import cv2
import numpy as np
import threading

# --- Network Configurations ---
HOST = "192.168.0.101"  
CTRL_PORT = 5000         
PORT_MAIN = 5001        
PORT_BOTTOM = 5002      
PORT_AUX = 5003         

# --- SCREEN INTERNAL 1080P VIRTUAL LAYOUT ---
WIDTH, HEIGHT = 1920, 1080

# --- DYNAMIC RATIO CONFIGURATION ---
MAIN_RATIO = 0.7  
LEFT_W = int(WIDTH * MAIN_RATIO)     
RIGHT_W = WIDTH - LEFT_W             
HALF_H = HEIGHT // 2                

# --- Thread-Safe Overwrite Locks ---
frame_locks = {
    "main": threading.Lock(),
    "bottom": threading.Lock(),
    "aux": threading.Lock()
}

shared_frames = {
    "main": None,
    "bottom": None,
    "aux": None,
    "running": True
}

def video_receiver_worker(port, dict_key, cam_name):
    print(f"[{cam_name}] Initializing Stream UDP listener on Port {port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", port))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2097152) # 放大緩衝區
    except Exception as e:
        print(f"[{cam_name} ERROR] UDP Binding failed: {e}")
        return

    while shared_frames["running"]:
        try:
            # 每一包都是一幅獨立且完整的畫面
            packet, _ = sock.recvfrom(65536)
            if not packet: continue
            
            np_arr = np.frombuffer(packet, dtype=np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                # 僅在寫入全域變數時鎖住 0.1 毫秒，絕不卡頓
                with frame_locks[dict_key]:
                    shared_frames[dict_key] = frame
                        
        except Exception as ex:
            print(f"[{cam_name}] UDP Link error: {ex}")
            break
            
    sock.close()
    print(f"[{cam_name}] UDP Listener cleanly terminated.")

def main():
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("[CRITICAL] Xbox Joystick not detected!")
        sys.exit()

    joystick = pygame.joystick.Joystick(0)
    joystick.init()

    screen = pygame.display.set_mode((1600, 900), pygame.RESIZABLE)
    pygame.display.set_caption("NKUST ROV STATION - HIGH SPEED COLOR HUD")

    virtual_canvas = pygame.Surface((WIDTH, HEIGHT))

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((HOST, CTRL_PORT))
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception as e:
        print("[Control Link Error] Connection failed:", e)
        sys.exit()

    threading.Thread(target=video_receiver_worker, args=(PORT_MAIN, "main", "CAM_MAIN"), daemon=True).start()
    threading.Thread(target=video_receiver_worker, args=(PORT_BOTTOM, "bottom", "CAM_BOTTOM"), daemon=True).start()
    threading.Thread(target=video_receiver_worker, args=(PORT_AUX, "aux", "CAM_AUX"), daemon=True).start()

    font = pygame.font.SysFont("arial", 24)
    running = True
    DEADZONE = 0.15          
    clock = pygame.time.Clock()

    cam_order = ["main", "bottom", "aux"]
    q_key_pressed = False

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False

        keys = pygame.key.get_pressed()
        msg = ["0"] * 18                                   

        if keys[pygame.K_ESCAPE]:
            msg[17] = "1"                
            running = False

        if keys[pygame.K_q]:
            if not q_key_pressed:
                cam_order.append(cam_order.pop(0))
                q_key_pressed = True
        else:
            q_key_pressed = False

        try:
            raw_joy_x = joystick.get_axis(0)  
            raw_joy_y = joystick.get_axis(1)  
        except:
            raw_joy_x, raw_joy_y = 0.0, 0.0

        joy_x = raw_joy_x if abs(raw_joy_x) > DEADZONE else 0.0
        joy_y = -raw_joy_y if abs(raw_joy_y) > DEADZONE else 0.0

        btn_lb = joystick.get_button(4)   
        btn_rb = joystick.get_button(5)   
        joy_v = 1.0 if btn_rb else (-1.0 if btn_lb else 0.0)

        msg[1] = f"{joy_x:.4f}"           
        msg[2] = f"{joy_y:.4f}"           
        msg[3] = f"{joy_v:.4f}"           

        if keys[pygame.K_a]: msg[5] = "1"      
        if keys[pygame.K_d]: msg[6] = "1"      

        data_str = ",".join(msg)
        try:
            client.sendall((data_str + "\n").encode())
        except:
            running = False

        virtual_canvas.fill((0, 0, 0)) 

        # --- HUD Tactical Dividers ---
        pygame.draw.line(virtual_canvas, (0, 255, 0), (LEFT_W, 0), (LEFT_W, HEIGHT), 2)
        pygame.draw.line(virtual_canvas, (0, 255, 0), (LEFT_W, HALF_H), (WIDTH, HALF_H), 2)

        def get_scaled_frame(key, max_w, max_h):
            # 【修復 3：搬離鎖區】只鎖住拿取畫面的瞬間
            with frame_locks[key]:
                frame = shared_frames[key]
                
            if frame is not None:
                # 耗時的縮放與色彩轉換移到「鎖外」，讓 UDP 接收執行緒可以瘋狂收包不被卡死
                h, w = frame.shape[:2]
                scale = min(max_w / w, max_h / h)
                new_w = int(w * scale)
                new_h = int(h * scale)
                
                resized_frame = cv2.resize(frame, (new_w, new_h))
                rgb_scaled = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
                surf = pygame.image.frombuffer(rgb_scaled.tobytes(), (new_w, new_h), "RGB")
                return surf, new_w, new_h
            return None, 0, 0

        # 1. POSITION: Left Half
        target_key_0 = cam_order[0]
        surf_0, sw_0, sh_0 = get_scaled_frame(target_key_0, LEFT_W, HEIGHT)
        if surf_0:
            ox = (LEFT_W - sw_0) // 2
            oy = (HEIGHT - sh_0) // 2
            virtual_canvas.blit(surf_0, (ox, oy))
        else:
            tag_err = font.render(f"WAITING FOR {target_key_0.upper()}...", True, (255, 60, 60))
            virtual_canvas.blit(tag_err, (LEFT_W // 2 - 120, HEIGHT // 2 - 14))

        # 2. POSITION: Top Right
        target_key_1 = cam_order[1]
        surf_1, sw_1, sh_1 = get_scaled_frame(target_key_1, RIGHT_W, HALF_H)
        if surf_1:
            ox = LEFT_W + (RIGHT_W - sw_1) // 2
            oy = (HALF_H - sh_1) // 2
            virtual_canvas.blit(surf_1, (ox, oy))
        else:
            tag_err = font.render(f"WAITING FOR {target_key_1.upper()}...", True, (255, 60, 60))
            virtual_canvas.blit(tag_err, (LEFT_W + RIGHT_W // 2 - 140, HALF_H // 2 - 14))

        # 3. POSITION: Bottom Right
        target_key_2 = cam_order[2]
        surf_2, sw_2, sh_2 = get_scaled_frame(target_key_2, RIGHT_W, HALF_H)
        if surf_2:
            ox = LEFT_W + (RIGHT_W - sw_2) // 2
            oy = HALF_H + (HALF_H - sh_2) // 2
            virtual_canvas.blit(surf_2, (ox, oy))
        else:
            tag_err = font.render(f"WAITING FOR {target_key_2.upper()}...", True, (255, 60, 60))
            virtual_canvas.blit(tag_err, (LEFT_W + RIGHT_W // 2 - 140, HALF_H + HALF_H // 2 - 14))

        # --- HUD Labels ---
        tag_0 = font.render(f"POS 1: {cam_order[0].upper()}", True, (0, 255, 0))
        tag_1 = font.render(f"POS 2: {cam_order[1].upper()}", True, (0, 255, 0))
        tag_2 = font.render(f"POS 3: {cam_order[2].upper()}", True, (0, 255, 0))
        virtual_canvas.blit(tag_0, (10, 10))
        virtual_canvas.blit(tag_1, (LEFT_W + 10, 10))
        virtual_canvas.blit(tag_2, (LEFT_W + 10, HALF_H + 10))

        # --- DYNAMIC CANVAS RESCALING ENGINE ---
        current_window_size = screen.get_size()
        scaled_hud = pygame.transform.scale(virtual_canvas, current_window_size)
        screen.blit(scaled_hud, (0, 0))

        pygame.display.flip()
        clock.tick(30)  

    shared_frames["running"] = False
    client.close()
    pygame.quit()

if __name__ == "__main__":
    main()