import cv2
from ultralytics import YOLO
import time
import os
import sys
import numpy as np

# 參數設定
CONFIDENCE_THRESHOLD = 0.7
MIN_BOX_SIZE = 15
MAX_DET = 50
SHRINK_RATE = 0.1

# 預設模式
IS_UNDERWATER_MODE = False 

CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
SAVE_DIR = "captured_rov_evidence"
if not os.path.exists(SAVE_DIR): os.makedirs(SAVE_DIR)

# 載入模型
current_dir = os.path.dirname(os.path.abspath(__file__))
model_path = os.path.join(current_dir, "best.pt")

try:
    print(f"讀取模型: {model_path}")
    model = YOLO(model_path)
except Exception as e:
    print(f"找不到 best.pt: {e}")
    sys.exit()

def enhance_underwater_image(image):
    try:
        image_blurred = cv2.GaussianBlur(image, (3, 3), 0)
        lab = cv2.cvtColor(image_blurred, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(12, 12))
        cl = clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    except:
        return image

# 啟動攝影機
print(f"啟動截圖分析模式 (預設: {'水下' if IS_UNDERWATER_MODE else '陸地'})...")
cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not cap.isOpened():
    print("無法開啟鏡頭")
    sys.exit()

actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"連線成功：{actual_w}x{actual_h}")
print("=========================================")
print("   [空白鍵] : 拍照")
print("   [M] 鍵   : 切換 陸地/水下 模式")
print("   [Q] 鍵   : 離開")
print("=========================================")

# 主迴圈
while True:
    success, raw_img = cap.read()
    if not success or raw_img is None:
        time.sleep(0.01)
        continue

    if IS_UNDERWATER_MODE:
        current_frame = enhance_underwater_image(raw_img)
        mode_text = "MODE: Underwater (Ready)"
        mode_color = (0, 255, 255) 
    else:
        current_frame = raw_img
        mode_text = "MODE: Air/Land (Ready)"
        mode_color = (0, 255, 0)

    # 製作顯示畫面
    display_img = cv2.resize(current_frame, (960, 720), interpolation=cv2.INTER_LINEAR)
    
    # 顯示狀態文字
    cv2.putText(display_img, mode_text, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, mode_color, 2)
    cv2.putText(display_img, "Press [SPACE] to Detect", (20, 680), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

    cv2.imshow('ROV Smart Vision', display_img)

    # 按鍵監聽
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'): 
        break

    elif key == ord('m'): # 切換模式
        IS_UNDERWATER_MODE = not IS_UNDERWATER_MODE
        print(f"切換模式: {'水下' if IS_UNDERWATER_MODE else '陸地'}")

    elif key == 32: # 空白鍵觸發截圖
        print("正在執行分析...")
        
        # 複製當前畫面進行分析
        analyze_img = current_frame.copy()
        
        # 執行偵測
        results = model(
            analyze_img, 
            conf=CONFIDENCE_THRESHOLD,
            iou=0.45,
            max_det=MAX_DET,
            imgsz=640,
            verbose=False
        )
        
        # 繪製結果
        detected_count = 0
        for r in results:
            boxes = r.boxes
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                
                w, h = x2 - x1, y2 - y1
                # 尺寸過濾
                if w < MIN_BOX_SIZE or h < MIN_BOX_SIZE: continue

                # 縮框處理
                pad_w = int(w * SHRINK_RATE / 2)
                pad_h = int(h * SHRINK_RATE / 2)
                nx1, ny1, nx2, ny2 = x1+pad_w, y1+pad_h, x2-pad_w, y2-pad_h
                if nx2 <= nx1 or ny2 <= ny1: continue

                # 顏色邏輯 
                name = model.names[cls_id]
                name_lower = name.lower()
                color = (0, 0, 255) # 預設紅色

                if "green" in name_lower:
                    color = (0, 255, 0)
                elif "rock" in name_lower and "native" in name_lower:
                    color = (0, 255, 255) 

                # 畫框與文字
                cv2.rectangle(analyze_img, (nx1, ny1), (nx2, ny2), color, 2)
                label = f"{name} {conf:.2f}"
                if w >= 30:
                    cv2.putText(analyze_img, label, (nx1, ny1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                detected_count += 1
        
        # 4. 存檔
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{SAVE_DIR}/Evidence_{ts}_count{detected_count}.jpg"
        cv2.imwrite(filename, analyze_img)
        print(f"已存檔: {filename}")
        
        # 5. 顯示結果暫停1.5秒
        result_display = cv2.resize(analyze_img, (960, 720))
        cv2.rectangle(result_display, (0,0), (960, 720), (255, 255, 255), 10) # 閃爍白框提示
        cv2.putText(result_display, f"CAPTURED! Found: {detected_count}", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        
        cv2.imshow('ROV Smart Vision', result_display)
        cv2.waitKey(1500) # 暫停1.5秒

cap.release()
cv2.destroyAllWindows()
