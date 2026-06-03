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

"""电源配置"""
rd.AnalogIOChannelEnableSet(0, True)
rd.AnalogIOChannelNodeSet(0, 3.3)

"""DMM配置"""
rd.DMMOpen(True)
rd.DMMSet(RDDMMDCV, 1)

# 等待1秒至输出稳定
time.sleep(1)

# 读取DMM读数
rd.RDDMMReadSingle()

print(type(rd.DMMData.value))
print(rd.DMMData.value)

# str_value = rd.DMMData.value.decode()
# print(type(str_value))
# print(str_value)

# float_value = float(str_value[:-1])
# print(type(float_value))
# print(float_value)

"""善后工作"""
# 关闭电源
rd.AnalogIOChannelEnableSet(0, False)
# 关闭DMM
rd.DMMOpen(False)
# 关闭设备
rd.DeviceClose()
