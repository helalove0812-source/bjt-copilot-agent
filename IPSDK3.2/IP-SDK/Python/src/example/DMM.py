# -*- coding: utf-8 -*-
"""
Created on Thu Mar 20 17:26:55 2025

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
print(rd.DeviceOpen(1))
#DMM 

print(rd.DMMOpen(True))#打开dmm
print(rd.DMMSet(RDDMMDCV,2))
print(rd.RDDMMReadSingle())
    
print(rd.DMMData.value)
print(rd.DMMbacksize.value)
# close connect
print(rd.DMMOpen(False))#关闭dmm

print(rd.DeviceClose())