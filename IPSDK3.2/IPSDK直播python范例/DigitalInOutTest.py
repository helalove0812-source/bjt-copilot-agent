# -*- coding: utf-8 -*-
"""
DIO2 输出 1kHz 时钟信号 (Pulse)
DIO3 输出随机信号 (Random)
DIO0/DIO1 接收并绘制波形
"""

import time

import numpy as np
import matplotlib.pyplot as plt

import sys
# 将 IP-SDK (Python) 添加到系统环境变量 PATH 中
# 请根据实际安装路径修改以下路径
sys.path.append(r'C:\YZKJ\IP-SDK\Python\src')
from pyRD import RD
from pyRD.core.RDconstant import *

# 创建 RD 类的实例
rd = RD()

# 枚举并打印可用的设备列表
rd.DeviceEnumLists()
print(f"Available devices: {rd.devicelist}")

# 查找序列号包含 'YZ' 的设备
usb_port = None
for i, device in enumerate(rd.devicelist):
    device_sn = device[1].decode()
    if 'YZ' in device_sn:
        usb_port = i

# 未找到设备报错
if usb_port is None:
    raise(RuntimeError("Device not found."))

# 获取匹配设备的序列号
device_sn = rd.devicelist[usb_port][1].decode()
print(f"Unit SN: {device_sn}")

# 打开设备
status = rd.DeviceOpen(usb_port)

# ============================================================
# DigitalOut 配置: DIO2 = 1kHz 时钟, DIO3 = 随机
# ============================================================
div = int(20e6 / 1e3)  # 20MHz / 1kHz = 20000

chEnables = [0, 0, 1, 1] + [0] * 12
chTypes   = [0, 0, RDDigitalOutTypePulse, RDDigitalOutTypeRandom] + [0] * 12
divs      = [0, 0, div, div] + [0] * 12
idles     = [0, 0, 0, 0] + [0] * 12
divinit   = [0, 0, 0, 0] + [0] * 12
counter_l = [1, 1, 1, 1] + [1] * 12
counter_h = [1, 1, 1, 1] + [1] * 12

rd.DigitalOutTriggerSourceSet(RDTRIGSRCNone)
rd.DigitalOutEnableSet(0x0C)  # DIO2 + DIO3 = 0b1100

for i in range(16):
    if chEnables[i] == 0:
        continue
    rd.DigitalOutTypeSet(i, chTypes[i])
    rd.DigitalOutIdleSet(i, idles[i])
    rd.DigitalOutDividerSet(i, divs[i])
    if chTypes[i] == RDDigitalOutTypePulse:
        rd.DigitalOutCounterInitSet(i, idles[i], divinit[i])
        rd.DigitalOutCounterSet(i, counter_l[i], counter_h[i])
    elif chTypes[i] == RDDigitalOutTypeRandom:
        rd.DigitalOutCounterSet(i, 1, 1)

# 启动数字输出
rd.DigitalOutRun(True)

# 等待输出稳定
time.sleep(0.1)

# ============================================================
# DigitalIn 配置: DIO0/DIO1 采集, 400kHz 采样率
# ============================================================
in_div = int(40e6 / 400e3)  # 400kHz 采样率
buffersize = 2048

rd.DigitalInDividerSet(in_div)
rd.DigitalInBufferSizeSet(buffersize)
rd.DigitalInChannelSet(0x03)  # DIO0 + DIO1

rd.DigitalInTriggerSourceSet(RDTRIGSRCDetectorDigitalIn)
rd.DigitalInTriggerTypeSet(RDTRIGTYPEEdge)
rd.DigitalInTriggerSlopeSet(RDTriggerSlopeRise)
rd.DigitalInTriggerTimeoutSet(1)  # 1秒超时
rd.DigitalInTriggerSet(0x01, 0x00)  # DIO0 上升沿触发

# 启动数字输入采集
rd.DigitalInConfigure(True)

rd.DigitalInStatus()
i = 0
while (rd.digitalinstatus != 2) and (i < 30):
    rd.DigitalInStatus()
    i += 1
    print(f"Status: {rd.digitalinstatus}")
    time.sleep(0.1)

# ============================================================
# 读取并绘制波形
# ============================================================
if rd.digitalinstatus == 2:
    rd.DigitalInRead(buffersize)
    print(f"Read back size: {rd.dibacksize}")

    rowlist = list(rd.didata)
    t = np.linspace(0, buffersize / 400e3 * 1000, buffersize)  # 时间轴 ms

    dio0 = [(rowlist[j] >> 0) & 1 for j in range(buffersize)]
    dio1 = [(rowlist[j] >> 1) & 1 for j in range(buffersize)]

    actual_size = rd.dibacksize.value if rd.dibacksize.value < buffersize else buffersize
    total_ms = actual_size / 400e3 * 1000
    ticks = np.arange(0, total_ms + 0.01, 1)

    plt.figure(figsize=(12, 5))

    plt.subplot(2, 1, 1)
    plt.plot(t[:actual_size], dio0[:actual_size], drawstyle='steps-post', color='blue')
    plt.ylabel("DIO0 (Clock)")
    plt.ylim(-0.2, 1.5)
    plt.xticks(ticks)
    plt.grid(True)
    plt.title("DIO0 <- DIO2 (1kHz Clock)")

    plt.subplot(2, 1, 2)
    plt.plot(t[:actual_size], dio1[:actual_size], drawstyle='steps-post', color='red')
    plt.ylabel("DIO1 (Random)")
    plt.xlabel("Time (ms)")
    plt.ylim(-0.2, 1.5)
    plt.xticks(ticks)
    plt.grid(True)
    plt.title("DIO1 <- DIO3 (Random)")

    plt.tight_layout()
    plt.show()
else:
    print("DigitalIn acquisition failed (timeout).")

# ============================================================
# 关闭
# ============================================================
rd.DigitalInConfigure(False)
rd.DigitalOutRun(False)
rd.DeviceClose()
