import ctypes,time
from ctypes import wintypes
from PIL import ImageGrab
u=ctypes.windll.user32
h=u.FindWindowW(None,'奶娃：大学四年')
class R(ctypes.Structure): _fields_=[('left',ctypes.c_long),('top',ctypes.c_long),('right',ctypes.c_long),('bottom',ctypes.c_long)]
r=R(); u.GetWindowRect(h,ctypes.byref(r)); box=(r.left,r.top,r.right,r.bottom); print('hwnd',h,'box',box,'fg',u.GetForegroundWindow())
u.ShowWindow(h,5); u.BringWindowToTop(h); u.SetForegroundWindow(h); time.sleep(.5)
ImageGrab.grab(bbox=box).save('reports/review/before_key.png')
u.keybd_event(0x44,0,0,0); time.sleep(1.5); u.keybd_event(0x44,0,2,0); time.sleep(.3)
ImageGrab.grab(bbox=box).save('reports/review/after_key.png'); print('fg2',u.GetForegroundWindow())
