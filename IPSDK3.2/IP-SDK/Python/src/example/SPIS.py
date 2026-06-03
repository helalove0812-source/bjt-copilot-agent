# -*- coding: utf-8 -*-
"""
Created on Thu Jul 13 15:15:49 2023

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

#SPIS

rd.SPISPECIALSwitch(True)#open all
rd.SPISPECIALPluseSwitch(True)#open pluse
rd.SPISPECIALIOSwitch(0)#IO5 6 7 9 10 11;
# set 0表示000000;
# set 1表示110000；
# set 2表示001000；
# set 3表示110110；
# set 4表示001011；
#rd.SPISPECIALRead(30)#read SPI
for i in range(0,10):
    time.sleep(0.1)
    rd.SPISPECIALRead(30)
    if rd.SPISbacksize.value>0:
        break
print(list(rd.SPISdata)[0:rd.SPISbacksize.value],rd.SPISbacksize)

# close connect
rd.SPISPECIALSwitch(False)

print(rd.DeviceClose())