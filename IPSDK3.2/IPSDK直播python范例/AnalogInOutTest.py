# -*- coding: utf-8 -*-
"""
IP-SDK 快速入门 Python 示例程序
功能：控制信号源输出 4V/1kHz 正弦波，然后通过示波器获取该波形数据并绘图

来源：#1_IP_SDK_快速入门.pdf - Python示例代码 (第9-12页)
"""

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

"""示波器配置"""
# 定义示波器配置参数的数据类
@dataclass
class AnalogInParams:
    ch: int
    range: int
    freq: float
    trig_timeout: float
    trig_src: int
    trig_type: int
    trig_slope: int
    trig_level: float
    buffersize: int

# 定义应用示波器配置参数的函数
def AnalogInApplyConfig(rd, ai):
    rd.AnalogInCHEnable(ai.ch, True)
    rd.AnalogInCHRangeSet(ai.ch, ai.range)
    rd.AnalogInFrequencySet(ai.freq)
    rd.AnalogInTriggerAutoTimeoutSet(ai.trig_timeout)
    rd.AnalogInTriggerSourceSet(ai.trig_src)
    rd.AnalogInTriggerTypeSet(ai.trig_type)
    rd.AnalogInTriggerConditionSet(ai.trig_slope)
    rd.AnalogInTriggerLevelSet(ai.trig_level, ai.range)
    rd.AnalogInBufferSizeSet(ai.buffersize)

# 创建一套示波器的配置参数，命名为 ai0
ai0 = AnalogInParams(
    ch=0,                                    # CH1
    range=5,                                 # 量程：5V
    freq=400e3,                              # 采样率：400kHz
    trig_timeout=0,                          # 自动触发时间：永不自动触发
    trig_src=RDTRIGSRCDetectorAnalogInCH1,   # 触发源：CH1
    trig_type=RDTRIGTYPEEdge,                # 触发方式：边沿触发
    trig_slope=RDTriggerSlopeRise,           # 触发方向：上升沿触发
    trig_level=0,                            # 触发电平：0V
    buffersize=4096,                         # 缓冲区大小：4096 字节
)

# 应用示波器配置 ai0
AnalogInApplyConfig(rd, ai0)

"""信号源配置"""
# 定义信号源配置参数的数据类
@dataclass
class AnalogOutParams:
    ch: int
    node: int
    func: int
    freq: float
    amp: float
    offset: float
    symmetry: int
    phase: int

# 定义应用信号源配置参数的函数
def AnalogOutApplyConfig(rd, ao):
    rd.AnalogOutNodeEnableSet(ao.ch, ao.node, True)
    rd.AnalogOutNodeFunctionSet(ao.ch, ao.node, ao.func)
    rd.AnalogOutNodeFrequencySet(ao.ch, ao.node, ao.freq)
    rd.AnalogOutNodeOffsetAmpSet(ao.ch, ao.node, ao.offset, ao.amp)
    rd.AnalogOutNodeSymmetrySet(ao.ch, ao.node, ao.symmetry)
    rd.AnalogOutNodePhaseSet(ao.ch, ao.node, ao.phase)

# 创建一套信号源的配置参数，命名为 ao0
ao0 = AnalogOutParams(
    ch=0,                            # CH1
    node=RDAnalogOutNodeCarrier,     # 节点：载波节点
    func=RDFUNCSine,                 # 波形函数：正弦波
    freq=1000,                       # 频率：1kHz
    offset=0,                        # 偏置：0V
    amp=4,                           # 幅值：4V
    symmetry=50,                     # 对称性：50
    phase=0,                         # 相位：0
)

# 应用信号源配置 ao0
AnalogOutApplyConfig(rd, ao0)

"""运行设备"""
# 启动信号源
rd.AnalogOutConfigure(ao0.ch, True)

# 等待1秒至输出稳定
time.sleep(1)

# 启动示波器
rd.AnalogInRun(True)

# 检查示波器状态是否就绪
success = False
for _ in range(10):               # 最多尝试 10次
    rd.AnalogInStatus()           # 获取当前状态
    if rd.analoginstatus == 2:    # 状态为2表示采集完成
        success = True
        break

# 信号采集失败报错
if not success:
    raise(RuntimeError('Scope reading failed.'))

# 读取采集到的数据
rd.AnalogInRead(ai0.buffersize, ai0.ch)

# 打印读取到的数据点数
print(f"Size of data read: {rd.aibacksizech1}")

# 使用 matplotlib 绘制采集到的波形
x = np.linspace(0, 1 / ai0.freq * ai0.buffersize * 1000, ai0.buffersize)
y = np.array(rd.aidatach1)
plt.plot(x, y)
plt.grid(True)
plt.xlabel("Time/ms")
plt.ylabel("CH1/V")
plt.title(f"{device_sn} Analog Out-In Test")
plt.show()

"""善后工作"""
# 关闭信号源
rd.AnalogOutConfigure(ao0.ch, False)
# 关闭示波器
rd.AnalogInRun(False)
# 关闭设备
rd.DeviceClose()
