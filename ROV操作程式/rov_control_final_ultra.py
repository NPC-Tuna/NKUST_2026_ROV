import socket
import pygame
import math
import os
import time

# --- CONFIGURATION ---
PI_IP = "192.168.0.102"
PORT = 5000
FRAME_RATE = 20

# --- INITIALIZE SOCKET ---
def connect_to_pi():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((PI_IP, PORT))
        return s
    except Exception as e:
        print(f"Error: Could not connect to Pi at {PI_IP}:{PORT}")
        print(f"Reason: {e}")
        return None

# --- INITIALIZE PYGAME ---
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("Error: No joystick detected!")
    exit()

joystick = pygame.joystick.Joystick(0)
joystick.init()

# --- HELPER FUNCTIONS ---
def get_bar(val, length=10):
    fraction = (val + 1) / 2
    filled = int(fraction * length)
    filled = max(0, min(length, filled))
    return "[" + "#" * filled + " " * (length - filled) + "]"

def reset_cursor():
    """將游標移回左上角，但不清除螢幕，這是解決閃爍的關鍵。"""
    print("\033[H", end="")

# --- MAIN LOOP ---
sock = connect_to_pi()
if not sock:
    exit()

# 程式開始前清一次螢幕，之後都用覆蓋的
os.system('cls' if os.name == 'nt' else 'clear')

try:
    clock = pygame.time.Clock()
    while True:
        pygame.event.pump()

        # 1. READ ANALOG STICKS
        lx = joystick.get_axis(0)
        ly = joystick.get_axis(1) * -1
        rx = joystick.get_axis(2)
        ry = joystick.get_axis(3) * -1
        
        ll = (lx**2 + ly**2)**0.5
        lo = (math.degrees(math.atan2(ly, lx)) + 360) % 360
        rl = (rx**2 + ry**2)**0.5

        # 2. READ BUTTONS
        # A=夾爪開, B=夾爪關, X=重置方向, Y=自動返航
        a, b, x, y = [joystick.get_button(i) for i in range(4)]
        lb, rb = joystick.get_button(4), joystick.get_button(5)  # LB=上升, RB=下降
        dx, dy = joystick.get_hat(0)

        # 3. LOCAL MOTOR ESTIMATION (dashboard only, pi_control.py calculates its own)
        m1 = ly + lx
        m2 = ly - lx
        m3, m4 = m1, m2
        motors = [max(-1, min(1, m)) for m in [m1, m2, m3, m4]]

        # 4. SEND DATA TO PI
        # Format (18 fields) matches pi_control.py index definitions:
        # [0]=cmd, [1]=lx, [2]=ly, [3]=rx, [4]=ry,
        # [5]=KEY_A(gripper_open), [6]=KEY_D(gripper_close),
        # [7]=BTN_RESET, [8]=BTN_AUTO_RET, [9-14]=padding,
        # [15]=BTN_ASCEND, [16]=BTN_DESCEND, [17]=BTN_DISCON
        msg = (f"C,"
               f"{lx:.3f},{ly:.3f},{rx:.3f},{ry:.3f},"
               f"{a},{b},{x},{y},"
               f"0,0,0,0,0,0,"
               f"{lb},{rb},0\n")
        
        try:
            sock.sendall(msg.encode())
        except:
            break

        # 5. RENDER DASHBOARD (解決閃爍)
        reset_cursor()
        print(f"=== VSCODE CONTROLLER DASHBOARD: {joystick.get_name()[:20]:<20} ===")
        print(f"Target IP: {PI_IP:<15} | Frequency: {FRAME_RATE}Hz         ")
        print("-" * 65)
        
        print(" [ JOYSTICK AXES ]                                               ")
        print(f"  Left Stick  : X:{lx:>6.2f} {get_bar(lx)}  Y:{ly:>6.2f} {get_bar(ly)}")
        print(f"  Right Stick : X:{rx:>6.2f} {get_bar(rx)}  Y:{ry:>6.2f} {get_bar(ry)}")
        print(f"  Vector      : Magnitude: {ll:.2f} | Angle: {lo:>5.1f}°             ")
        print("-" * 65)

        print(" [ BUTTONS ]                                                     ")
        print(f"  A[{'X' if a else ' '}]=夾爪開  B[{'X' if b else ' '}]=夾爪關  X[{'X' if x else ' '}]=重置方向  Y[{'X' if y else ' '}]=自動返航   ")
        print(f"  LB[{'X' if lb else ' '}]=上升   RB[{'X' if rb else ' '}]=下降   D-Pad: X:{dx:>2}, Y:{dy:>2}               ")
        print("-" * 65)

        print(" [ MOTOR OUTPUT ESTIMATION ]                                     ")
        print(f"  Front:  M1:{motors[0]:>6.2f}   M2:{motors[1]:>6.2f}                        ")
        print(f"  Rear :  M3:{motors[2]:>6.2f}   M4:{motors[3]:>6.2f}                        ")
        print("-" * 65)
        print(" Press Ctrl+C to disconnect and exit.                            ")

        clock.tick(FRAME_RATE)

except KeyboardInterrupt:
    print("\n\nDisconnecting...")
    try:
        disconnect_msg = "C,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1\n"
        sock.sendall(disconnect_msg.encode())
        time.sleep(0.1)
    except Exception:
        pass
finally:
    sock.close()
    pygame.quit()