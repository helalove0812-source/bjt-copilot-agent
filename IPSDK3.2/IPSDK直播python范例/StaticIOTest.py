# -*- coding: utf-8 -*-

from dataclasses import dataclass
import time

import numpy as np
import matplotlib.pyplot as plt

import sys
# 将 IP-SDK (Python) 添加到系统环境变量 PATH 中
# 请根据实际安装路径修改以下路径
sys.path.append('C:\YZKJ\IP-SDK\Python\src')
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

"""StaticIO配置"""
rd.DigitalIOOutputEnableSet(0xC)
rd.DigitalIOOutputSet(0x4)

# 等待1秒至输出稳定
time.sleep(1)

# 读取StaticIO状态
rd.DigitalIOInputStatus()

print(type(rd.stiodata.value))
print(rd.stiodata.value)
print(bin(rd.stiodata.value))

# 多次读取确保数值正确
# for i in range(5):
#     rd.DigitalIOInputStatus()
#     print(bin(rd.stiodata.value))
#     time.sleep(1)

"""善后工作"""
# 关闭StaticIO
rd.DigitalIOOutputEnableSet(0)
# 关闭设备
rd.DeviceClose()
