import socket
import pygame
import time
import sys
import cv2
import numpy as np
import select
import math

# 系統與網路設定
HOST = "192.168.0.101" 
PORT = 5000
DEADZONE = 0.05 

COLOR_THEME = {
    "primary": (0, 200, 255),
    "success": (0, 255, 128),
    "warning": (255, 200, 50),
    "danger": (255, 50, 50),
    "bg_dark": (5, 10, 15, 180),
    "text": (200, 220, 255)
}

def apply_deadzone(value, deadzone=DEADZONE):
    if abs(value) < deadzone:
        return 0.0
    return value

def draw_joystick(surface, x, y, val_x, val_y, title, font):
    temp_surface = pygame.Surface((140, 140), pygame.SRCALPHA)
    center = 70
    radius = 55
    pygame.draw.circle(temp_surface, (0, 255, 128, 80), (center, center), radius, 2)
    pygame.draw.line(temp_surface, (40, 60, 80, 120), (center, 0), (center, 140), 1)
    pygame.draw.line(temp_surface, (40, 60, 80, 120), (0, center), (140, center), 1)
    dot_x = center + int(val_x * radius)
    dot_y = center - int(val_y * radius) 
    pygame.draw.line(temp_surface, COLOR_THEME["success"], (center, center), (dot_x, dot_y), 2)
    pygame.draw.circle(temp_surface, COLOR_THEME["success"], (dot_x, dot_y), 6)
    surface.blit(temp_surface, (x - center, y - center))
    title_surface = font.render(title, True, COLOR_THEME["text"])
    val_surface = font.render(f"X:{val_x:+.2f} Y:{val_y:+.2f}", True, COLOR_THEME["primary"])
    surface.blit(title_surface, (x - title_surface.get_width()//2, y - center - 25))
    surface.blit(val_surface, (x - val_surface.get_width()//2, y + center + 10))

def draw_status_box(surface, x, y, w, h, title, status_text, is_active, font, active_color=COLOR_THEME["success"]):
    bg_color = COLOR_THEME["bg_dark"] if is_active else (2, 5, 8, 120)
    border_color = active_color if is_active else (100, 100, 100)
    bg_surface = pygame.Surface((w, h), pygame.SRCALPHA)
    bg_surface.fill(bg_color)
    pygame.draw.rect(bg_surface, border_color, (0, 0, w, h), 2, border_radius=5)
    pygame.draw.polygon(bg_surface, border_color, [(0, 10), (10, 0), (0, 0)]) 
    surface.blit(bg_surface, (x, y))
    title_surf = font.render(title, True, (150, 170, 180))
    status_surf = font.render(status_text, True, border_color)
    surface.blit(title_surf, (x + 15, y + 10))
    surface.blit(status_surf, (x + 15, y + 35))

def draw_motor_gauge(surface, x, y, w, h, title, percentage, font, color=COLOR_THEME["primary"]):
    percentage = max(min(percentage, 1.0), -1.0)
    gauge_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    gauge_surf.fill(COLOR_THEME["bg_dark"])
    pygame.draw.rect(gauge_surf, color, (0, 0, w, h), 2, border_radius=2)
    center_y = h // 2
    bar_height = int(abs(percentage) * (h / 2))
    if percentage >= 0:
        pygame.draw.rect(gauge_surf, color, (2, center_y - bar_height, w - 4, bar_height))
    else:               
        pygame.draw.rect(gauge_surf, color, (2, center_y, w - 4, bar_height))
    pygame.draw.line(gauge_surf, (150, 150, 150), (0, center_y), (w, center_y), 2)
    surface.blit(gauge_surf, (x, y))
    title_surf = font.render(title, True, COLOR_THEME["text"])
    val_surf = font.render(f"{percentage*100:+.0f}%", True, color)
    pygame.draw.rect(surface, (0, 0, 0, 150), (x - 5, y - 25, title_surf.get_width() + 10, 20))
    surface.blit(title_surf, (x + (w - title_surf.get_width())//2, y - 25))
    pygame.draw.rect(surface, (0, 0, 0, 150), (x - 10, y + h + 5, val_surf.get_width() + 20, 20))
    surface.blit(val_surf, (x + (w - val_surf.get_width())//2, y + h + 5))

def draw_artificial_horizon(surface, x, y, pitch, roll, font):
    radius = 65
    temp_surf = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
    center = radius
    pygame.draw.circle(temp_surf, COLOR_THEME["bg_dark"], (center, center), radius)
    pygame.draw.circle(temp_surf, COLOR_THEME["primary"], (center, center), radius, 2)
    pitch_offset = max(min(pitch * 1.5, radius - 10), -(radius - 10))
    line_width = 100
    line_surf = pygame.Surface((line_width, 4), pygame.SRCALPHA)
    line_surf.fill(COLOR_THEME["success"])
    rotated_line = pygame.transform.rotate(line_surf, -roll) 
    line_rect = rotated_line.get_rect(center=(center, center + int(pitch_offset)))
    temp_surf.blit(rotated_line, line_rect)
    pygame.draw.line(temp_surf, COLOR_THEME["warning"], (center - 15, center), (center + 15, center), 3)
    pygame.draw.circle(temp_surf, COLOR_THEME["danger"], (center, center), 4)
    surface.blit(temp_surf, (x - radius, y - radius))
    title_surf = font.render("ARTIFICIAL HORIZON", True, COLOR_THEME["text"])
    p_text = font.render(f"P: {pitch:+.1f}", True, COLOR_THEME["primary"])
    r_text = font.render(f"R: {roll:+.1f}", True, COLOR_THEME["success"])
    surface.blit(title_surf, (x - title_surf.get_width()//2, y - radius - 25))
    surface.blit(p_text, (x - radius, y + radius + 10))
    surface.blit(r_text, (x + radius - r_text.get_width(), y + radius + 10))

def draw_hud_crosshair(surface, width, height):
    cx, cy = width // 2, height // 2
    color = (0, 255, 128, 120)
    pygame.draw.line(surface, color, (cx - 30, cy), (cx - 10, cy), 2)
    pygame.draw.line(surface, color, (cx + 10, cy), (cx + 30, cy), 2)
    pygame.draw.line(surface, color, (cx, cy - 30), (cx, cy - 10), 2)
    pygame.draw.line(surface, color, (cx, cy + 10), (cx, cy + 30), 2)
    pygame.draw.circle(surface, color, (cx, cy), 3, 0)

def draw_distance_lines(surface, width, height):
    cx = width // 2
    levels = [
        {"y": int(height * 0.60), "hw": 140, "color": COLOR_THEME["success"]}, 
        {"y": int(height * 0.75), "hw": 240, "color": COLOR_THEME["warning"]}, 
        {"y": int(height * 0.90), "hw": 380, "color": COLOR_THEME["danger"]}  
    ]
    temp_surf = pygame.Surface((width, height), pygame.SRCALPHA)
    top_l = (cx - levels[0]["hw"], levels[0]["y"])
    top_r = (cx + levels[0]["hw"], levels[0]["y"])
    bot_l = (cx - levels[-1]["hw"], levels[-1]["y"])
    bot_r = (cx + levels[-1]["hw"], levels[-1]["y"])
    
    pygame.draw.line(temp_surf, (255, 255, 255, 60), top_l, bot_l, 2)
    pygame.draw.line(temp_surf, (255, 255, 255, 60), top_r, bot_r, 2)

    for lvl in levels:
        y, hw = lvl["y"], lvl["hw"]
        color = list(lvl["color"]) + [160] 
        pygame.draw.line(temp_surf, color, (cx - hw, y), (cx + hw, y), 3)
        pygame.draw.line(temp_surf, color, (cx - hw, y - 15), (cx - hw, y), 3)
        pygame.draw.line(temp_surf, color, (cx + hw, y - 15), (cx + hw, y), 3)
    surface.blit(temp_surf, (0, 0))

def main():
    pygame.init()
    pygame.joystick.init()

    has_joystick = pygame.joystick.get_count() > 0
    joystick = None
    if has_joystick:
        joystick = pygame.joystick.Joystick(0)
        joystick.init()
        print(f"已連接搖桿: {joystick.get_name()}")
    else:
        print("DEMO模式未偵測到搖桿，將啟用鍵盤模擬搖桿操作。")

    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    WIDTH, HEIGHT = screen.get_size()

    pygame.display.set_caption("Abyss-OS 2.0 :: ROV FPV COMMAND CENTER (DEMO MODE)")
    sys_font_large = pygame.font.SysFont("courier", 26, bold=True)
    sys_font_mid = pygame.font.SysFont("courier", 18, bold=True)
    sys_font_small = pygame.font.SysFont("courier", 14)

    # 攝影機初始化
    print("啟動攝影機系統...")
    cap_main = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap_rear = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    
    # 網路連線
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    network_status = "ROV DISCONNECTED (DEMO MODE)"
    network_color = COLOR_THEME["warning"] 
    
    try:
        client.settimeout(1.0) 
        client.connect((HOST, PORT))
        client.settimeout(None) 
        network_status = f"LINK ESTABLISHED :: {HOST}:{PORT}"
        network_color = COLOR_THEME["success"]
    except Exception:
        print("未連線到實體 ROV，將啟用模擬數據流...")

    telemetry = {"pitch": 0.0, "roll": 0.0, "yaw": 0.0, "depth": 0.0, "temp": 0.0}
    prev_btn_a = False
    hover_lock_state = False
    running = True
    clock = pygame.time.Clock()

    try:
        while running:
            pygame.event.pump()
            keys = pygame.key.get_pressed() 
            msg = ["0"] * 18

            # 離開條件
            if keys[pygame.K_ESCAPE] or (has_joystick and joystick.get_button(7)): 
                msg[17] = "1"
                running = False
            
            # 讀取輸入
            joy_lx, joy_ly, joy_rx, joy_ry = 0.0, 0.0, 0.0, 0.0
            btn_lb, btn_rb, btn_a, btn_rear_cam_trigger = False, False, False, False

            if has_joystick:
                joy_lx = apply_deadzone(joystick.get_axis(0))
                joy_ly = apply_deadzone(-joystick.get_axis(1)) 
                joy_rx = apply_deadzone(joystick.get_axis(2) if joystick.get_numaxes() > 2 else 0.0)
                joy_ry = apply_deadzone(-joystick.get_axis(3) if joystick.get_numaxes() > 3 else 0.0)
                btn_lb = joystick.get_button(4) 
                btn_rb = joystick.get_button(5) 
                btn_a = joystick.get_button(0)
                if joystick.get_numaxes() > 5:
                    btn_rear_cam_trigger = joystick.get_axis(5) > 0.0
            else:
                # 鍵盤模擬操作配置
                # 左搖桿 (平移) 方向鍵
                if keys[pygame.K_UP]: joy_ly = 1.0
                if keys[pygame.K_DOWN]: joy_ly = -1.0
                if keys[pygame.K_LEFT]: joy_lx = -1.0
                if keys[pygame.K_RIGHT]: joy_lx = 1.0
                
                # 右搖桿 (轉向/俯仰) I, J, K, L 鍵
                if keys[pygame.K_i]: joy_ry = 1.0
                if keys[pygame.K_k]: joy_ry = -1.0
                if keys[pygame.K_j]: joy_rx = -1.0
                if keys[pygame.K_l]: joy_rx = 1.0

                # 垂直升降 Q, E 鍵
                btn_lb = keys[pygame.K_q] # Q鍵上升 (對應搖桿 LB)
                btn_rb = keys[pygame.K_e] # E鍵下降 (對應搖桿 RB)
                
                # 姿態保持 (Attitude Hold) - H 鍵
                btn_a = keys[pygame.K_h]  # 對應搖桿 A 鍵

            # 夾爪控制 (無論是否有搖桿，都允許鍵盤 A/D 介入)
            btn_grip_open = keys[pygame.K_a] 
            btn_grip_close = keys[pygame.K_d] 
            
            # 如果沒有右板機，或處於純鍵盤模式，用空白鍵觸發後視鏡
            if not btn_rear_cam_trigger:
                btn_rear_cam_trigger = keys[pygame.K_SPACE] 

            trigger_hover_signal = False
            if btn_a and not prev_btn_a:
                msg[7] = "1"  
                trigger_hover_signal = True
                hover_lock_state = not hover_lock_state
            prev_btn_a = btn_a

            msg[1], msg[2], msg[3], msg[4] = f"{joy_lx:.3f}", f"{joy_ly:.3f}", f"{joy_rx:.3f}", f"{joy_ry:.3f}"
            if btn_grip_open: msg[5] = "1"  
            if btn_grip_close: msg[6] = "1"  
            if btn_lb: msg[15] = "1"
            if btn_rb: msg[16] = "1"

            data_str = ",".join(msg)
            
            # 處理Socket或產生DEMO假數據
            if running and "LINK" in network_status:
                try:
                    client.sendall((data_str + "\n").encode())
                    ready_to_read, _, _ = select.select([client], [], [], 0)
                    if ready_to_read:
                        recv_data = client.recv(1024).decode()
                        if recv_data:
                            lines = recv_data.strip().split('\n')
                            latest_data = lines[-1].split(',')
                            if len(latest_data) >= 5:
                                telemetry["pitch"] = float(latest_data[0])
                                telemetry["roll"] = float(latest_data[1])
                                telemetry["depth"] = float(latest_data[3])
                                telemetry["temp"] = float(latest_data[4])
                except:
                    network_status = "ROV DISCONNECTED"
                    network_color = COLOR_THEME["danger"]
            else:
                # DEMO模式數據模擬
                t = time.time()
                telemetry["pitch"] = math.sin(t * 0.8) * 15  # 模擬水下晃動
                telemetry["roll"] = math.cos(t * 0.5) * 20
                telemetry["depth"] = 5.0 + math.sin(t * 0.2) * 1.5
                telemetry["temp"] = 24.5

            ret_main, frame_main = cap_main.read() if cap_main.isOpened() else (False, None)
            
            if ret_main:
                main_frame = cv2.resize(frame_main, (WIDTH, HEIGHT))
                frame_rgb = cv2.cvtColor(main_frame, cv2.COLOR_BGR2RGB)
                frame_surface = pygame.image.frombuffer(frame_rgb.tobytes(), (WIDTH, HEIGHT), "RGB")
                screen.blit(frame_surface, (0, 0))
            else:
                # DEMO無訊號背景
                screen.fill((10, 25, 40)) 
                no_signal_text = sys_font_large.render("NO CAMERA SIGNAL", True, (100, 100, 120))
                screen.blit(no_signal_text, (WIDTH//2 - no_signal_text.get_width()//2, HEIGHT//2))
            
            draw_distance_lines(screen, WIDTH, HEIGHT)
            draw_hud_crosshair(screen, WIDTH, HEIGHT)

            # 頂部狀態列
            pygame.draw.rect(screen, (0, 0, 0, 180), (0, 0, WIDTH, 45))
            pygame.draw.line(screen, COLOR_THEME["primary"], (0, 45), (WIDTH, 45), 2)
            sys_title = sys_font_large.render("Abyss-OS 2.0 :: MATEROV COMMAND", True, COLOR_THEME["text"])
            net_status = sys_font_mid.render(network_status, True, network_color)
            screen.blit(sys_title, (20, 10))
            screen.blit(net_status, (WIDTH - net_status.get_width() - 20, 13))

            # 左側UI區塊
            vert_thrust = 1.0 if btn_lb else (-1.0 if btn_rb else 0.0)
            
            h_fl = joy_ly + joy_lx + joy_rx 
            h_fr = joy_ly - joy_lx - joy_rx  
            h_rl = joy_ly - joy_lx + joy_rx  
            h_rr = joy_ly + joy_lx - joy_rx  
            v_fl = vert_thrust + joy_ry      
            v_fr = vert_thrust + joy_ry      
            v_rl = vert_thrust - joy_ry      
            v_rr = vert_thrust - joy_ry      

            left_ui_x = 30
            spacing = 52     

            draw_motor_gauge(screen, left_ui_x + 0*spacing, 90, 22, 100, "H-FL", h_fl, sys_font_small, COLOR_THEME["success"])
            draw_motor_gauge(screen, left_ui_x + 1*spacing, 90, 22, 100, "H-FR", h_fr, sys_font_small, COLOR_THEME["success"])
            draw_motor_gauge(screen, left_ui_x + 2*spacing, 90, 22, 100, "H-RL", h_rl, sys_font_small, COLOR_THEME["success"])
            draw_motor_gauge(screen, left_ui_x + 3*spacing, 90, 22, 100, "H-RR", h_rr, sys_font_small, COLOR_THEME["success"])

            draw_motor_gauge(screen, left_ui_x + 0*spacing, 235, 22, 100, "V-FL", v_fl, sys_font_small, COLOR_THEME["primary"])
            draw_motor_gauge(screen, left_ui_x + 1*spacing, 235, 22, 100, "V-FR", v_fr, sys_font_small, COLOR_THEME["primary"])
            draw_motor_gauge(screen, left_ui_x + 2*spacing, 235, 22, 100, "V-RL", v_rl, sys_font_small, COLOR_THEME["primary"])
            draw_motor_gauge(screen, left_ui_x + 3*spacing, 235, 22, 100, "V-RR", v_rr, sys_font_small, COLOR_THEME["primary"])

            draw_status_box(screen, left_ui_x, 380, 230, 65, "VERTICAL DRIVE", "ASCENDING" if btn_lb else "DESCENDING" if btn_rb else "AUTO-DEPTH", btn_lb or btn_rb, sys_font_mid, COLOR_THEME["primary"])
            draw_status_box(screen, left_ui_x, 460, 230, 65, "GRIPPER (A/D)", "OPENING" if btn_grip_open else "CLOSING" if btn_grip_close else "HOLD", btn_grip_open or btn_grip_close, sys_font_mid, COLOR_THEME["warning"])
            
            joystick_y = HEIGHT - 130
            draw_joystick(screen, left_ui_x + 70, joystick_y, joy_lx, joy_ly, "LEFT STICK", sys_font_small)
            draw_joystick(screen, left_ui_x + 210, joystick_y, joy_rx, joy_ry, "RIGHT STICK", sys_font_small)

            # 右側 UI 區塊 
            right_ui_x = WIDTH - 280
            draw_artificial_horizon(screen, right_ui_x + 125, 180, telemetry["pitch"], telemetry["roll"], sys_font_small)
            
            depth_str = f"D: {telemetry['depth']:.2f} m"
            temp_str = f"T: {telemetry['temp']:.1f} °C"
            draw_status_box(screen, right_ui_x, 280, 250, 65, "MAZU TELEMETRY", f"{depth_str} | {temp_str}", True, sys_font_mid, COLOR_THEME["success"])
            draw_status_box(screen, right_ui_x, 360, 250, 65, "ATTITUDE HOLD", "RESETTING!" if trigger_hover_signal else "LOCKED" if hover_lock_state else "STANDBY", hover_lock_state, sys_font_mid, (200, 100, 255))

            # 彈出式上方後視鏡
            if btn_rear_cam_trigger:
                rear_w, rear_h = 360, 200 
                rear_x = (WIDTH - rear_w) // 2 
                rear_y = 55 
                
                pygame.draw.rect(screen, COLOR_THEME["bg_dark"], (rear_x, rear_y, rear_w, rear_h))
                pygame.draw.rect(screen, COLOR_THEME["warning"], (rear_x-2, rear_y-2, rear_w+4, rear_h+4), 3) 
                
                ret_rear, frame_rear = cap_rear.read() if cap_rear.isOpened() else (False, None)
                if ret_rear:
                    rear_display_frame = cv2.flip(frame_rear, 1) 
                    rear_display_frame = cv2.resize(rear_display_frame, (rear_w, rear_h))
                    rear_frame_rgb = cv2.cvtColor(rear_display_frame, cv2.COLOR_BGR2RGB)
                    rear_surface = pygame.image.frombuffer(rear_frame_rgb.tobytes(), (rear_w, rear_h), "RGB")
                    screen.blit(rear_surface, (rear_x, rear_y))
                else:
                    # 無後鏡頭時的模擬畫面
                    pygame.draw.line(screen, (100,0,0), (rear_x, rear_y), (rear_x+rear_w, rear_y+rear_h), 2)
                    pygame.draw.line(screen, (100,0,0), (rear_x+rear_w, rear_y), (rear_x, rear_y+rear_h), 2)
                    
                cx = rear_x + rear_w // 2
                by = rear_y + rear_h
                pygame.draw.line(screen, (255, 200, 50, 180), (cx - 50, by), (cx - 20, rear_y + 60), 2)
                pygame.draw.line(screen, (255, 200, 50, 180), (cx + 50, by), (cx + 20, rear_y + 60), 2)
                
                rear_title = sys_font_small.render(" REARVIEW MIRROR (ACTIVE) ", True, (0, 0, 0))
                pygame.draw.rect(screen, COLOR_THEME["warning"], (rear_x, rear_y, rear_title.get_width(), 20))
                screen.blit(rear_title, (rear_x, rear_y + 2))

            # 底部資料流狀態
            pygame.draw.rect(screen, (0, 0, 0, 220), (0, HEIGHT - 35, WIDTH, 35))
            trigger_status = " [SPACE PRESSED: REAR MIRROR ON] " if btn_rear_cam_trigger else ""
            raw_text = sys_font_small.render(f"TX DATASTREAM > {data_str}{trigger_status}", True, (80, 255, 80))
            screen.blit(raw_text, (20, HEIGHT - 25))

            pygame.display.flip()
            clock.tick(20) 

    except KeyboardInterrupt:
        print("\n使用者強制中斷。")
    except Exception as e:
        print(f"\n發生錯誤: {e}")
    finally:
        exit_msg = ["0"] * 18
        exit_msg[17] = "1"
        try:
            client.sendall((",".join(exit_msg) + "\n").encode())
        except:
            pass
        client.close()
        cap_main.release() 
        cap_rear.release() 
        pygame.quit()
        print("程式已安全結束。")

if __name__ == "__main__":
    main()
