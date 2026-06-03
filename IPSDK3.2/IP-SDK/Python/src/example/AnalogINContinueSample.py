# -*- coding: utf-8 -*-
"""
Created on Tue Mar 28 09:59:58 2023

@author: jackscl
"""

import matplotlib.pyplot as plt
import numpy as np
import time
import sys,os
import pathlib
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

# analogout config
print(rd.AnalogOutNodeEnableSet(0,0,True))
rd.AnalogOutNodeFunctionSet(0,0,1)
rd.AnalogOutNodeFrequencySet(0,0,2000)
rd.AnalogOutNodeOffsetAmpSet(0,0,0,1)
rd.AnalogOutNodeSymmetrySet(0,0,50)
rd.AnalogOutNodePhaseSet(0,0,0)
rd.AnalogOutConfigure(0,True)

time.sleep(1)
#analogIn config

in_ch=0 #0 or 1 for channel 1 or 2
in_range=5 #5 or 25
in_fre=1e5
value_ch1=[]
value_ch2=[]

buffersize=102200
csamples=0 
cAvailable=5110
rd.AnalogInCHEnable(in_ch,True)
rd.AnalogInCHRangeSet(in_ch,in_range)
rd.AnalogInFrequencySet(in_fre)


#analogIn status read
rd.AnalogInContinueRun(True)
   
#analogIn data read
while(csamples<buffersize):

    if(cAvailable>buffersize-csamples):
        cAvailable=buffersize-csamples
    rd.AnalogInContinueRead(cAvailable,0)#5110 a block
    csamples=csamples+rd.aibacksizech1.value
    for i in range(5):
        value=list(rd.aidatach1)
        value_ch1+=value_ch1+value[i*1022:511+i*1022]
        value_ch2+=value_ch2+value[i*1022+511:(i+1)*1022]
    print(csamples)

plt.plot(value)
# close all instruments
print(rd.AnalogInContinueRun(False))
# close connect
print(rd.DeviceClose())