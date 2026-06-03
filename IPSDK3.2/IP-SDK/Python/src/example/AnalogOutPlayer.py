# -*- coding: utf-8 -*-
"""
Created on Tue Mar 28 10:00:11 2023

@author: jackscl
"""

import matplotlib.pyplot as plt
import numpy as np
import time
import sys,os
import pathlib
import wave
py_path, py_name = os.path.split(os.path.abspath(__file__))

base_dir = pathlib.Path(py_path).absolute().parent #sys.argv[0]
 
if sys.path.count(base_dir) == 0:
    sys.path.append(str(base_dir))
 
from pyRD import RD
from pyRD.core.RDconstant import *


rd=RD()
rd.DeviceEnumLists()
print(rd.devicelist)
print(rd.DeviceOpen(0))
#analogout config
fw=wave.open("../../../jazz.wav","r")#get music file
chscount=fw.getnchannels()
sampwidth=fw.getsampwidth()
totalsize=fw.getnframes()
fre=fw.getframerate()
pos = 0
cAvailable=2048
node=RDAnalogOutNodeCarrier
func=RDFUNCPlay

amp=1.0
offset=0
str_data=fw.readframes(totalsize)
wave_data=np.fromstring(str_data, dtype=np.short)
wave_data.shape=-1,2
wave_data=wave_data.T/32768.0
fw.close()
#config wavegen player

rd.AnalogOutNodeEnableSet(0,node,True)
rd.AnalogOutNodeFunctionSet(0,node,func)
rd.AnalogOutNodeFrequencySet(0,node,fre)
rd.AnalogOutNodeOffsetAmpSet(0,node,offset,amp)
rd.AnalogOutNodeEnableSet(1,node,True)
rd.AnalogOutNodeFunctionSet(1,node,func)
rd.AnalogOutNodeFrequencySet(1,node,fre)
rd.AnalogOutNodeOffsetAmpSet(1,node,offset,amp)
rd.AnalogOutNodePlayerEnableSet(0,True)
rd.AnalogOutNodePlayerEnableSet(1,True)

rd.AnalogOutConfigure(2,True)
rd.AnalogOutNodePlayerRun(True)
ret=0
# send player data
while pos <totalsize:
    rd.analogoutPlayerstatus=0
    while(rd.analogoutPlayerstatus!=2)&(ret==0):
        ret=rd.AnalogOutNodePlayerCheck()
        time.sleep(0.001)
    if rd.analogoutPlayerstatus==2:
        if pos+cAvailable>totalsize:
            cAvailable=totalsize-pos
        ret=rd.AnalogOutNodePlayerDataSet(0,wave_data[0][pos:pos+cAvailable])
        ret=rd.AnalogOutNodePlayerDataSet(1,wave_data[1][pos:pos+cAvailable])
        pos+=cAvailable
    if ret!=0:
        break
    #print("pos:"+str(pos))

# close all instruments


rd.AnalogOutNodePlayerRun(False)
print(rd.AnalogOutConfigure(2,False))
rd.AnalogOutNodePlayerEnableSet(0,False)
rd.AnalogOutNodePlayerEnableSet(1,False)
# close connect
print(rd.DeviceClose())