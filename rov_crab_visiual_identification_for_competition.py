import cv2
import torch
import numpy as np
import os
import sys
import time
from ultralytics import YOLO

# 匯入 FUnIE-GAN 結構
from funie_generator import GeneratorFunieGAN 

# 將信心度門檻從 0.7 降到 0.35，避免過濾掉稍微不確定的目標
CONFIDENCE_THRESHOLD = 0.65
# 將最小目標尺寸從 15 降到 5，讓遠處或較小的物件也能被抓到
MIN_BOX_SIZE = 5 

MAX_DET = 50
SHRINK_RATE = 0.1
IS_UNDERWATER_MODE = False 
CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
SAVE_DIR = "captured_rov_evidence"
if not os.path.exists(SAVE_DIR): os.makedirs(SAVE_DIR)


current_dir = os.path.dirname(os.path.abspath(__file__))
yolo_model_path = os.path.join(current_dir, "best.pt")
gan_weights_path = os.path.join(current_dir, "funie_generator.pth") 

# 1. 喚醒 YOLO
try:
    print(f"[*] 正在讀取 YOLO 模型: {yolo_model_path}")
    yolo_model = YOLO(yolo_model_path)
except Exception as e:
    print(f"找不到 YOLO 權重 (best.pt): {e}")
    sys.exit()

# 2. 喚醒 FUnIE-GAN
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
try:
    print(f"[*] 正在讀取 FUnIE-GAN 水下還原引擎: {gan_weights_path}")
    gan_model = GeneratorFunieGAN()
    state_dict = torch.load(gan_weights_path, map_location=device)
    # 處理可能的多GPU前綴
    if list(state_dict.keys())[0].startswith('module.'):
        state_dict = {k.replace('module.', ''): v for k, v in state_dict.items()}
    gan_model.load_state_dict(state_dict)
    gan_model = gan_model.to(device)
    gan_model.eval()
    print(f"[*] FUnIE-GAN 載入成功！(運算核心: {device})")
except Exception as e:
    print(f"FUnIE-GAN 載入失敗，請確認檔名是否為 funie_generator.pth: {e}")
    sys.exit()

def enhance_underwater_image_gan(image):
    h, w = image.shape[:2]
    img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    img_resized = cv2.resize(img_rgb, (256, 256))
    img_tensor = (img_resized / 127.5) - 1.0  
    img_tensor = torch.tensor(img_tensor, dtype=torch.float32).permute(2, 0, 1).unsqueeze(0).to(device)

    with torch.no_grad():
        fake_tensor = gan_model(img_tensor)
    
    out_img = fake_tensor.squeeze().permute(1, 2, 0).cpu().numpy()
    out_img = ((out_img + 1.0) * 127.5).clip(0, 255).astype(np.uint8)
    out_img = cv2.resize(out_img, (w, h))
    final_bgr = cv2.cvtColor(out_img, cv2.COLOR_RGB2BGR)
    return final_bgr


print("\n>>> 啟動雙 AI 截圖分析系統 <<<")
cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

if not cap.isOpened():
    print("無法開啟鏡頭")
    sys.exit()

print("=========================================")
print("   [空白鍵] : 執行分析與拍照")
print("   [M] 鍵   : 切換 陸地 / FUnIE-GAN水下模式")
print("   [Q] 鍵   : 離開")
print("=========================================")

while True:
    success, raw_img = cap.read()
    if not success or raw_img is None:
        time.sleep(0.01)
        continue

    if IS_UNDERWATER_MODE:
        current_frame = enhance_underwater_image_gan(raw_img)
        mode_text = "MODE: FUnIE-GAN Underwater"
        mode_color = (0, 255, 255) 
    else:
        current_frame = raw_img 
        mode_text = "MODE: Air/Land"
        mode_color = (0, 255, 0)

    display_img = cv2.resize(current_frame, (960, 720))
    cv2.putText(display_img, mode_text, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, mode_color, 2)
    cv2.putText(display_img, "Press [SPACE] to Detect", (20, 680), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

    cv2.imshow('ROV Smart Vision', display_img)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'): 
        break
    elif key == ord('m'):
        IS_UNDERWATER_MODE = not IS_UNDERWATER_MODE
        print(f"[*] 切換模式: {'FUnIE-GAN 水下還原' if IS_UNDERWATER_MODE else '陸地原始畫面'}")
    elif key == 32: # 空白鍵
        print(">>> 執行 YOLO 分析...")
        analyze_img = current_frame.copy()
        
        # 將iou從 0.45 調高到 0.6，允許目標之間有更多的重疊（避免擠在一起的目標被當成同一個）
        results = yolo_model(
            analyze_img, conf=CONFIDENCE_THRESHOLD, iou=0.6, max_det=MAX_DET, imgsz=640, verbose=False, device=0
        )
        
        detected_count = 0
        for r in results:
            boxes = r.boxes
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                w, h = x2 - x1, y2 - y1
                if w < MIN_BOX_SIZE or h < MIN_BOX_SIZE: continue

                pad_w, pad_h = int(w * SHRINK_RATE / 2), int(h * SHRINK_RATE / 2)
                nx1, ny1, nx2, ny2 = x1+pad_w, y1+pad_h, x2-pad_w, y2-pad_h
                if nx2 <= nx1 or ny2 <= ny1: continue

                name = yolo_model.names[cls_id]
                color = (0, 255, 0) if "green" in name.lower() else (0, 255, 255) if "rock" in name.lower() else (0, 0, 255)
                
                cv2.rectangle(analyze_img, (nx1, ny1), (nx2, ny2), color, 2)
                
                cv2.putText(analyze_img, f"{name} {conf:.2f}", (nx1, ny1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                
                detected_count += 1
        
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{SAVE_DIR}/Evidence_{ts}.jpg"
        cv2.imwrite(filename, analyze_img)
        print(f"[*] 證據已存檔: {filename} (共偵測到 {detected_count} 個目標)")
        
        result_display = cv2.resize(analyze_img, (960, 720))
        cv2.rectangle(result_display, (0,0), (960, 720), (255, 255, 255), 10) 
        cv2.putText(result_display, f"CAPTURED! Found: {detected_count}", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        cv2.imshow('ROV Smart Vision', result_display)
        cv2.waitKey(1500) 

cap.release()
cv2.destroyAllWindows()
