import pyautogui
import time

print("Move your mouse to the TOP-LEFT of the Chrome window...")
time.sleep(3)
x1, y1 = pyautogui.position()
print(f"Start coordinates: ({x1}, {y1})")

print("Move your mouse to the BOTTOM-RIGHT of the Chrome window...")
time.sleep(3)
x2, y2 = pyautogui.position()
print(f"Region: left={x1}, top={y1}, width={x2-x1}, height={y2-y1}")