import time
import numpy as np
import asyncio

import sys
import os

# 动态将雨骤 SDK 路径注入到系统环境变量中，确保能找到 pyRD 模块
# 注意：这里硬编码了当前电脑的绝对路径，如果是部署到其他电脑，需要修改此路径
SDK_PATH = '/Users/helap/Documents/雨骤/IPSDK3.2/IP-SDK/Python/src'
if os.path.exists(SDK_PATH) and SDK_PATH not in sys.path:
    sys.path.append(SDK_PATH)

try:
    from pyRD import RD
    from pyRD.core.RDconstant import *
    # 测试实例化，如果在无硬件连接或驱动缺失时 dll 会报错
    _test_rd = RD()
    del _test_rd
    HAS_HARDWARE = True
except Exception as e:
    print(f"Hardware init warning (using simulation mode): {e}")
    HAS_HARDWARE = False

class BJTTester:
    def __init__(self):
        self.rd = RD() if HAS_HARDWARE else None
        self.is_running = False
        self.device_type = "UNKNOWN"
        
        # 硬件电路常数与缩放因子
        # AWG 0-5V -> 经外置功放 -> 0-50V
        self.VCE_SCALE = 10.0  
        # 取样电阻
        self.Rb_sense = 100.0  # Ω
        self.Rc_sense = 1.0    # Ω
        
    def connect(self):
        if not HAS_HARDWARE:
            return True
        self.rd.DeviceEnumLists()
        for i, device in enumerate(self.rd.devicelist):
            if b'YZ' in device[1]:
                status = self.rd.DeviceOpen(i)
                if status == 0:
                    self.setup_hardware()
                    return True
        return False

    def setup_hardware(self):
        # 静态 IO 设置，用于控制继电器进行 NPN/PNP 切换
        self.rd.DigitalIOOutputEnableSet(0x0001) 
        
        # 配置 AWG1 和 AWG2 为直流模式
        self.rd.AnalogOutNodeEnableSet(0, RDAnalogOutNodeCarrier, True)
        self.rd.AnalogOutNodeFunctionSet(0, RDAnalogOutNodeCarrier, RDFUNCDC)
        self.rd.AnalogOutNodeEnableSet(1, RDAnalogOutNodeCarrier, True)
        self.rd.AnalogOutNodeFunctionSet(1, RDAnalogOutNodeCarrier, RDFUNCDC)
        
        # 配置示波器 4个通道 (用于读取 V_B, V_C, Vb_sense, Vc_sense)
        for ch in range(4):
            self.rd.AnalogInCHEnable(ch, True)
            self.rd.AnalogInCHRangeSet(ch, 5) # 5V 量程
        
        self.rd.AnalogInFrequencySet(100000) # 100kHz 采样率
        self.rd.AnalogInBufferSizeSet(1024)

    def detect_device(self):
        if not HAS_HARDWARE:
            self.device_type = "NPN"
            return self.device_type
            
        # 简单的极性探测逻辑：
        # 1. 继电器切向 NPN
        self.rd.DigitalIOOutputSet(0x0000)
        self.rd.AnalogOutNodeOffsetAmpSet(0, RDAnalogOutNodeCarrier, vOffset=1.0, amp=0)
        self.rd.AnalogOutNodeOffsetAmpSet(1, RDAnalogOutNodeCarrier, vOffset=2.0, amp=0)
        self.rd.AnalogOutConfigure(0, True)
        self.rd.AnalogOutConfigure(1, True)
        time.sleep(0.1)
        
        self.rd.AnalogInRun(True)
        while self.rd.AnalogInStatus() != 2:
            pass
        self.rd.AnalogInRead(1024, 3) # CH4 -> Vc_sense
        vc_sense = np.mean(self.rd.aidatach4)
        
        if vc_sense > 0.05: # 探测到明显电流
            self.device_type = "NPN"
        else:
            self.device_type = "PNP"
            
        self.rd.AnalogOutConfigure(0, False)
        self.rd.AnalogOutConfigure(1, False)
        return self.device_type

    async def run_sweep(self, params, callback):
        self.is_running = True
        ib_start = float(params.get('ib_start', 10))
        ib_step = float(params.get('ib_step', 10))
        steps = int(params.get('steps', 5))
        vce_max = float(params.get('vce_max', 5.0))
        ic_limit = float(params.get('ic_limit', 150))
        
        ib_values = [ib_start + i * ib_step for i in range(steps)]
        vce_values = np.linspace(0, vce_max, 50) # 每个阶梯扫描50个点
        
        if HAS_HARDWARE:
            self.rd.AnalogOutConfigure(0, True)
            self.rd.AnalogOutConfigure(1, True)
        
        for ib_target in ib_values:
            if not self.is_running: break
            
            # 设置 AWG1 输出对应基极电流 (硬件闭环或简单开环估算)
            # 这里简化为开环输出
            v_awg1 = (ib_target * 1e-6) * self.Rb_sense + 0.7 
            if HAS_HARDWARE:
                self.rd.AnalogOutNodeOffsetAmpSet(0, RDAnalogOutNodeCarrier, vOffset=min(v_awg1, 5.0), amp=0)
            
            for vce_target in vce_values:
                if not self.is_running: break
                
                # 设置 AWG2 扫描 Vce
                v_awg2 = vce_target / self.VCE_SCALE
                if HAS_HARDWARE:
                    self.rd.AnalogOutNodeOffsetAmpSet(1, RDAnalogOutNodeCarrier, vOffset=min(v_awg2, 5.0), amp=0)
                    time.sleep(0.01) # 稳定时间
                    
                    self.rd.AnalogInRun(True)
                    while self.rd.AnalogInStatus() != 2:
                        pass
                    
                    self.rd.AnalogInRead(1024, 0) # CH1: VB
                    self.rd.AnalogInRead(1024, 1) # CH2: VC
                    self.rd.AnalogInRead(1024, 2) # CH3: Vb_sense
                    self.rd.AnalogInRead(1024, 3) # CH4: Vc_sense
                    
                    v_b = np.mean(self.rd.aidatach1)
                    v_c = np.mean(self.rd.aidatach2)
                    vb_sense = np.mean(self.rd.aidatach3)
                    vc_sense = np.mean(self.rd.aidatach4)
                else:
                    # Simulation Mode
                    vb_sense = ib_target * 1e-6 * self.Rb_sense
                    vc_sense = (ib_target * 1e-6 * 100) * self.Rc_sense * (1 - np.exp(-vce_target*5)) # Mock transistor curve
                    v_b = 0.7
                    v_c = vce_target
                
                # 依据公式计算
                calc_ib = (vb_sense / self.Rb_sense) * 1e6 # uA
                calc_ic = (vc_sense / self.Rc_sense) * 1e3 # mA
                
                # 计算 Beta
                calc_beta = calc_ic / (calc_ib / 1000) if calc_ib > 0 else 0
                
                # 计算 VBE 和 VCE_SAT (近似，V_E = 0)
                v_e = 0.0
                vbe = v_b - v_e
                vce_sat = v_c - v_e if vce_target < 0.5 else 0.0 # 仅在饱和区有意义
                
                # 异常保护机制
                if calc_ic > ic_limit:
                    self.is_running = False
                    await callback({"error": "过流保护触发 (OCP)"})
                    if HAS_HARDWARE:
                        self.rd.AnalogOutConfigure(0, False)
                        self.rd.AnalogOutConfigure(1, False)
                    break
                    
                point = {
                    "Ib_target": ib_target,
                    "Vce": vce_target,
                    "Ic": calc_ic,
                    "Ib": calc_ib,
                    "Beta": calc_beta,
                    "VBE": vbe,
                    "VCE_SAT": vce_sat
                }
                await callback(point)
                await asyncio.sleep(0.01) # 让出事件循环
                
        if HAS_HARDWARE:
            self.rd.AnalogOutConfigure(0, False)
            self.rd.AnalogOutConfigure(1, False)
        self.is_running = False

    def stop(self):
        self.is_running = False
        if HAS_HARDWARE:
            self.rd.AnalogOutConfigure(0, False)
            self.rd.AnalogOutConfigure(1, False)
            self.rd.DeviceClose()
