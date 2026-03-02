import pygame
import math
import os

# 初始化 pygame 與 joystick 模組
pygame.init()
pygame.joystick.init()

# 偵測手把
if pygame.joystick.get_count() == 0:
    print("未偵測到手把，請連接控制器！")
    exit()

joystick = pygame.joystick.Joystick(0)
joystick.init()

# 輔助函式：產生類比數值的簡易視覺化量條
def get_bar(val, length=10):
    # 將 -1.0 ~ 1.0 映射到進度條 (0.0 為中心)
    fraction = (val + 1) / 2
    filled = int(fraction * length)
    # 確保數值不會超出範圍
    filled = max(0, min(length, filled))
    return "[" + "#" * filled + " " * (length - filled) + "]"

def clear_screen():
    # 使用 \033[H 讓游標回到左上角
    print("\033[H", end="")


# 第一次運行時先清空畫面
os.system('cls' if os.name == 'nt' else 'clear')

print(f"=== 控制器監控儀表板: {joystick.get_name()} ===")
print("-" * 75)

try:
    while True:
        pygame.event.pump()

        # 1. 讀取數據
        lx, ly = joystick.get_axis(0), joystick.get_axis(1) * -1
        rx, ry = joystick.get_axis(2), joystick.get_axis(3) * -1
        lt, rt = joystick.get_axis(4), joystick.get_axis(5)
        
        a, b, x, y = joystick.get_button(0), joystick.get_button(1), joystick.get_button(2), joystick.get_button(3)
        lb, rb = joystick.get_button(4), joystick.get_button(5)
        view, menu = joystick.get_button(6), joystick.get_button(7)
        ls_in, rs_in = joystick.get_button(8), joystick.get_button(9)
        
        dx, dy = joystick.get_hat(0)

        # 2. 運動邏輯計算
        m1 = m3 = ly + lx
        m2 = m4 = ly - lx

        # 3. 格式化排版輸出
        clear_screen()
        
        print(f"【 搖桿狀態 】")
        # --- 這裡將 X 和 Y 的 Bar 分開放在數值旁邊 ---
        print(f"  左搖桿 (L): X:{lx:>6.2f} {get_bar(lx)}  Y:{ly:>6.2f} {get_bar(ly)}")
        print(f"  右搖桿 (R): X:{rx:>6.2f} {get_bar(rx)}  Y:{ry:>6.2f} {get_bar(ry)}")
        print(f"  下壓按鈕:   L3: {'●' if ls_in else '○'}  R3: {'●' if rs_in else '○'}")
        print("-" * 75)

        print(f"【 扳機與肩鍵 】")
        print(f"  LT: {lt:>6.2f} {get_bar(lt)}  |  RT: {rt:>6.2f} {get_bar(rt)}")
        print(f"  LB: {'[按下]' if lb else '[放開]':<10}  |  RB: {'[按下]' if rb else '[放開]':<10}")
        print("-" * 75)

        print(f"【 動作按鈕 & 方向鍵 】")
        print(f"  A:{'■' if a else '□'}  B:{'■' if b else '□'}  X:{'■' if x else '□'}  Y:{'■' if y else '□'}  |  D-Pad: X:{dx:>2} Y:{dy:>2}")
        print(f"  選單: View:{'■' if view else '□'}  Menu:{'■' if menu else '□'}")
        print("-" * 75)

        print(f"【 馬達輸出預估 】")
        print(f"  M1:{m1:>6.2f}  M2:{m2:>6.2f}  M3:{m3:>6.2f}  M4:{m4:>6.2f}")
        print("-" * 75)
        print(" 按下 Ctrl+C 結束程式...")

        pygame.time.Clock().tick(30)

except KeyboardInterrupt:
    print("\n程式已停止。")
