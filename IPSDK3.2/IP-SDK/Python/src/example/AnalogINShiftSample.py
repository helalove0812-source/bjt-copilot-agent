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
import csv

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
in_fre=4e3
value_ch1=[]
value_ch2=[]

buffersize=102200
csamples=0 
cAvailable=5110
rd.AnalogInCHEnable(in_ch,True)
rd.AnalogInCHRangeSet(in_ch,in_range)
rd.AnalogInCHEnable(1,True)
rd.AnalogInCHRangeSet(1,in_range)
rd.AnalogInFrequencySet(in_fre)


#analogIn status read
rd.AnalogInShiftModeRun(True)

#analogIn data read
with open('test.csv', 'w', newline='') as csvfile:
    spamwriter = csv.writer(csvfile, delimiter=',',
                            quotechar='|', quoting=csv.QUOTE_MINIMAL)
    pos=0
    for i in range(100):
    
        rd.AnalogInShiftRead(0)#analog in ch1
        rd.AnalogInShiftRead(1)
        value_ch1+=list(rd.aidatach1)[0:rd.aibacksizech1.value]
        value_ch2+=list(rd.aidatach2)[0:rd.aibacksizech2.value]
        minisize=min(len(value_ch1),len(value_ch2))
        for j in range(minisize-pos):
            spamwriter.writerow([value_ch1[pos+j],value_ch2[pos+j]])
        #value_ch1[pos:minisize],value_ch2[pos:minisize])
        pos=minisize

        print("samples:"+str(rd.aibacksizech1.value))
        time.sleep(0.01)

plt.plot(value_ch1)
plt.plot(value_ch2)

# close all instruments
print(rd.AnalogInShiftModeRun(False))
# close connect
print(rd.DeviceClose())