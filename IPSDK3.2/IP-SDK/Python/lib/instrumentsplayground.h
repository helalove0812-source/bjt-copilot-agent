#ifndef INSTRUMENTSPLAYGROUND_H
#define INSTRUMENTSPLAYGROUND_H

//#include "InstrumentsPlayground_global.h"
#include <time.h>
#include <math.h>
#include <stdlib.h>
#include "ftd2xx.h"
#include <stdint.h>
#include <string.h>
#include <iostream>
#include <vector>
#include "sqlite/sqlite3.h"
#include <sstream>
#include <iomanip>

#ifndef RDAPI
    #if defined(WIN32)
        #if defined(__cplusplus)
            #define    RDAPI extern "C" __declspec(dllimport)
        #else
            #define    RDAPI __declspec(dllimport)
        #endif
    #else
        #if defined(__cplusplus)
            #define RDAPI extern "C"
        #else
            #define RDAPI
        #endif
    #endif
#endif
typedef unsigned char uchar;
typedef unsigned short uint16_t;
typedef unsigned int uint;

typedef signed short int16_t;
typedef signed int int32_t;
typedef signed int int32_t;

// trigger source
typedef BYTE RDTRIGSRC;
const RDTRIGSRC RDTRIGSRCNone                  = 0;
const RDTRIGSRC RDTRIGSRCDetectorAnalogInCH1   = 1;
const RDTRIGSRC RDTRIGSRCDetectorAnalogInCH2   = 2;
const RDTRIGSRC RDTRIGSRCDetectorAnalogInCH3   = 3;
const RDTRIGSRC RDTRIGSRCDetectorAnalogInCH4   = 4;
const RDTRIGSRC RDTRIGSRCDetectorDigitalIn     = 5;
const RDTRIGSRC RDTRIGSRCDigitalOut            = 6;
const RDTRIGSRC RDTRIGSRCManule                = 7;
const RDTRIGSRC RDTRIGSRCExternal1             = 8;
const RDTRIGSRC RDTRIGSRCExternal2             = 9;
const RDTRIGSRC RDTRIGSRCDigitalIn              =10;



// instrument states:
typedef BYTE RDState;
const RDState RDStateReady        = 0;
const RDState RDStateConfig       = 4;
const RDState RDStatePrefill      = 5;
const RDState RDStateArmed        = 1;
const RDState RDStateWait         = 7;
const RDState RDStateTriggered    = 3;//6
const RDState RDStateRunning      = 3;
const RDState RDStateDone         = 2;


// acquisition modes:
typedef int RDACQMODE;
const RDACQMODE RDACQMODESingle     = 0;
const RDACQMODE RDACQMODEScanShift  = 1;
const RDACQMODE RDACQMODEScanScreen = 2;
const RDACQMODE RDACQMODERecord     = 3;
const RDACQMODE RDACQMODEOvers      = 4;
const RDACQMODE RDACQMODESingle1    = 5;

// analog acquisition RDFILTER:
typedef int RDFILTER;
const RDFILTER RDFILTERDecimate = 0;
const RDFILTER RDFILTERAverage  = 1;
const RDFILTER RDFILTERMinMax   = 2;

// analog acquisition RDFILTER:
typedef int RDTriggerSlope;
const RDTriggerSlope RDTriggerSlopeRise   = 0;
const RDTriggerSlope RDTriggerSlopeFall   = 1;
const RDTriggerSlope RDTriggerSlopeEdge   = 2;

// analog in trigger mode:
typedef int RDTRIGTYPE;
const RDTRIGTYPE RDTRIGTYPEEdge         = 0;
const RDTRIGTYPE RDTRIGTYPEPulse        = 1;
const RDTRIGTYPE RDTRIGTYPETransition   = 2;


// analog in trigger length condition
typedef int RDTRIGLEN;
const RDTRIGLEN RDTRIGLENLess       = 0;
const RDTRIGLEN RDTRIGLENTimeout    = 1;
const RDTRIGLEN RDTRIGLENMore       = 2;

// error codes for RD Public API:
typedef int RDERC;
const   RDERC RDercNoErc                  = 0;        //  No error occurred
const   RDERC RDercUnknownError           = 1;        //  API waiting on pending API timed out
const   RDERC RDercApiLockTimeout         = 2;        //  API waiting on pending API timed out
const   RDERC RDercAlreadyOpened          = 3;        //  Device already opened
const   RDERC RDercNotSupported           = 4;        //  Device not supported
const   RDERC RDercInvalidParameter0      = 0x10;     //  Invalid parameter sent in API call
const   RDERC RDercInvalidParameter1      = 0x11;     //  Invalid parameter sent in API call
const   RDERC RDercInvalidParameter2      = 0x12;     //  Invalid parameter sent in API call
const   RDERC RDercInvalidParameter3      = 0x13;     //  Invalid parameter sent in API call
const   RDERC RDercInvalidParameter4      = 0x14;     //  Invalid parameter sent in API call

// analog out signal types
typedef BYTE RDFUNC;
const RDFUNC RDFUNCDC       = 0;
const RDFUNC RDFUNCSine     = 1;
const RDFUNC RDFUNCSquare   = 2;
const RDFUNC RDFUNCTriangle = 3;
const RDFUNC RDFUNCRampUp   = 4;
const RDFUNC RDFUNCRampDown = 5;
const RDFUNC RDFUNCNoise    = 6;
const RDFUNC RDFUNCPulse    = 7;
const RDFUNC RDFUNCTrapezium= 8;
const RDFUNC RDFUNCSinePower= 9;
const RDFUNC RDFUNCCustom   = 10;
const RDFUNC RDFUNCPlay     = 11;

// analog io channel node types
typedef BYTE RDANALOGIO;
const RDANALOGIO RDANALOGIOEnable       = 1;
const RDANALOGIO RDANALOGIOVoltage      = 2;
const RDANALOGIO RDANALOGIOCurrent      = 3;
const RDANALOGIO RDANALOGIOPower        = 4;
const RDANALOGIO RDANALOGIOTemperature  = 5;

typedef int RDAnalogOutNode;
const RDAnalogOutNode RDAnalogOutNodeCarrier  = 0;
const RDAnalogOutNode RDAnalogOutNodeFM       = 1;
const RDAnalogOutNode RDAnalogOutNodeAM       = 2;

typedef int RDAnalogOutMode;
const RDAnalogOutMode RDAnalogOutModeVoltage  = 0;
const RDAnalogOutMode RDAnalogOutModeCurrent  = 1;

typedef int RDAnalogOutIdle;
const RDAnalogOutIdle RDAnalogOutIdleDisable  = 0;
const RDAnalogOutIdle RDAnalogOutIdleOffset   = 1;
const RDAnalogOutIdle RDAnalogOutIdleInitial  = 2;

typedef int RDDigitalInClockSource;
const RDDigitalInClockSource RDDigitalInClockSourceInternal = 0;
const RDDigitalInClockSource RDDigitalInClockSourceExternal = 1;

typedef int RDDigitalInSampleMode;
const RDDigitalInSampleMode RDDigitalInSampleModeSimple   = 0;
// alternate samples: noise|sample|noise|sample|...
// where noise is more than 1 transition between 2 samples
const RDDigitalInSampleMode RDDigitalInSampleModeNoise    = 1;

typedef int RDDigitalOutOutput;
const RDDigitalOutOutput RDDigitalOutOutputPushPull   = 0;
const RDDigitalOutOutput RDDigitalOutOutputOpenDrain  = 1;
const RDDigitalOutOutput RDDigitalOutOutputOpenSource = 2;
const RDDigitalOutOutput RDDigitalOutOutputThreeState = 3; // for custom and random

typedef int RDDigitalOutType;
const RDDigitalOutType RDDigitalOutTypePulse      = 0;
const RDDigitalOutType RDDigitalOutTypeCustom     = 1;
const RDDigitalOutType RDDigitalOutTypeRandom     = 2;
const RDDigitalOutType RDDigitalOutTypeFSM        = 3;

typedef int RDDigitalOutIdle;
const RDDigitalOutIdle RDDigitalOutIdleInit     = 0;
const RDDigitalOutIdle RDDigitalOutIdleLow      = 1;
const RDDigitalOutIdle RDDigitalOutIdleHigh     = 2;
const RDDigitalOutIdle RDDigitalOutIdleZet      = 3;

typedef int RDDMMType;
const RDDMMType DMMDCV     = 0;
const RDDMMType DMMDCA      = 1;
const RDDMMType DMMACV     = 2;
const RDDMMType DMMACA      = 3;
const RDDMMType DMMR      = 4;
const RDDMMType Diode      = 5;

RDAPI int RDSDKVersion(char* Version);

RDAPI int RDEnumDeviceCount(DWORD * count);
RDAPI int RDEnumDeviceInfo (int i, char* Description,char* SerialNumber,FT_HANDLE *handle);
RDAPI int RDdeviceOpen(int i,FT_HANDLE *ftHandle);
RDAPI int RDdeviceClose(FT_HANDLE ftHandle);


RDAPI int RDAnalogInStatus(FT_HANDLE handle,RDState* sts);
RDAPI int RDAnalogInFrequencySet(FT_HANDLE handle,int fre);
RDAPI int RDAnalogInChannelRangeSet(FT_HANDLE handle,int channel,double range);
RDAPI int RDAnalogInChannelEnableSet(FT_HANDLE handle,int channel,bool enable);
RDAPI int RDAnalogInTriggerAutoTimeoutSet(FT_HANDLE handle, int timeout);//0
RDAPI int RDAnalogInTriggerSourceSet(FT_HANDLE handle,RDTRIGSRC trigsrc );//RDTRIGSRCDetectorAnalogIn
RDAPI int RDAnalogInTriggerTypeSet(FT_HANDLE handle, RDTRIGTYPE trigtype);
//        RDAnalogInTriggerChannelSet(ftHandle, m_scopeconfig.trigch);
RDAPI int RDAnalogInTriggerLevelSet(FT_HANDLE handle, double voltsLevel,int range,int ch,uchar* CalArray);
RDAPI int RDAnalogInTriggerConditionSet(FT_HANDLE handle, RDTriggerSlope trigcond);
RDAPI int RDAnalogInBufferSizeSet(FT_HANDLE handle, int buffersize);
//        RDAnalogInTriggerHoldOffSet(ftHandle,m_scopeconfig.holdoff);
//        RDAnalogInTriggerHysteresisSet(ftHandle,m_scopeconfig.HysteresisLevel);
RDAPI int RDAnalogInConfigure(FT_HANDLE handle,bool run);
RDAPI int RDAnalogInShiftModeRun(FT_HANDLE handle, bool open);

RDAPI int RDAnalogInContinueRun(FT_HANDLE handle,bool enable);
RDAPI int RDAnalogInContinueRead(FT_HANDLE handle, int size, double range_ch1, double range_ch2, double *RxBuffer, int offset, uchar *CalArray, int *backsize);

RDAPI int RDAnalogOutNodeEnableSet(FT_HANDLE handle,int ch, RDAnalogOutNode node, bool enable);
RDAPI int RDAnalogOutNodeFunctionSet(FT_HANDLE handle, int ch, RDAnalogOutNode node, RDFUNC func);
RDAPI int RDAnalogOutNodeFrequencySet(FT_HANDLE handle, int ch, RDAnalogOutNode node, double hzFrequency);
//RDAPI int RDAnalogOutNodeAmplitudeSet(FT_HANDLE handle, int ch, RDAnalogOutNode node, double vAmplitude);

//RDAPI int RDAnalogOutNodeOffsetSet(FT_HANDLE handle, int ch, RDAnalogOutNode node, double vOffset);//如果不加 void RDAnalogInStatus 会卡
RDAPI int RDAnalogOutNodeOffsetAmpSet(FT_HANDLE handle, int ch, RDAnalogOutNode node, double vOffset,double amp,uchar* CalArray);
RDAPI int RDAnalogOutNodeSymmetrySet(FT_HANDLE handle,int ch,RDAnalogOutNode node,double percentageSymmetry);
RDAPI int RDAnalogOutNodePhaseSet(FT_HANDLE handle,int ch,RDAnalogOutNode node,double degreePhase);
RDAPI int RDAnalogOutConfigure(FT_HANDLE handle, int ch, bool output);
RDAPI int RDAnalogOutNodeDataSet(FT_HANDLE handle,  int ch, RDAnalogOutNode node, double *rgdData, int cdData);

RDAPI int RDAnalogIOChannelNodeSet(FT_HANDLE handle,int ch,double value,uchar* CalArray) ;
RDAPI int RDAnalogIOChannelEnableSet(FT_HANDLE handle,int ch,int enable) ;

RDAPI int RDAnalogOutNodeSweepFreSet(FT_HANDLE handle,  int ch, int fre_start, int fre_stop,double timebase);
RDAPI int RDAnalogOutNodeSweepFreEnableSet(FT_HANDLE handle,  int ch, bool enable);
RDAPI int RDAnalogOutNodeSweepAmpSet(FT_HANDLE handle,  int ch, double amp_start, double amp_stop,double timebase,double vOffset,uchar* CalArray);
RDAPI int RDAnalogOutNodeSweepAmpEnableSet(FT_HANDLE handle,  int ch, bool enable);

RDAPI int RDAnalogOutNodePlayerEnableSet(FT_HANDLE handle ,int ch, bool enable);//both need enable
RDAPI int RDAnalogOutNodePlayerRun(FT_HANDLE handle, bool enable);//both start and stop,stop will exit play mode
RDAPI int RDAnalogOutNodePlayerCheck(FT_HANDLE handle,  uchar *sts);
RDAPI int RDAnalogOutNodePlayerDataSet(FT_HANDLE handle,int ch,  double* playData, int cdData);//8bit 2048  0 for less 2048

RDAPI int RDCalibrationWrite(FT_HANDLE handle,uchar *CalArray);
RDAPI int RDCalibrationRead(FT_HANDLE handle,uchar *CalArray);

RDAPI int AnalogInRead(FT_HANDLE handle,int ch,int size,char* RxBuffer,int *backsize);
RDAPI int RDAnalogInRead(FT_HANDLE handle,int ch, int size,double range, double *RxBuffer,uchar* CalArray,int *backsize);
RDAPI int RDAnalogInShiftRead(FT_HANDLE handle, int ch, double range, double *RxBuffer, uchar *CalArray, int *backsize);

//    int  RDDigitalInReset(FT_HANDLE handle);
//    int  RDDigitalInClockSourceSet(FT_HANDLE handle,RDDigitalInClockSource clocksource);
RDAPI int RDDigitalInDividerSet(FT_HANDLE handle,uint div);//div=MaxHz/samplerate
//    int  RDDigitalInSampleFormatSet(FT_HANDLE handle,int nBits);//nBits
//    int  RDDigitalInInputOrderSet(FT_HANDLE handle,int order);//# for Digital Discovery bit order: DIO24:39; with 32 bit sampling [DIO24:39 + DIN0:15]
RDAPI int RDDigitalInBufferSizeSet(FT_HANDLE handle,int buffersize);
RDAPI int RDDigitalInChannelSet(FT_HANDLE handle,int channel);

//    int  RDDigitalInSampleModeSet(FT_HANDLE handle,int samplemode);
//    int  RDDigitalInSampleSensibleSet(FT_HANDLE handle,int fs); //compression
//    int  RDDigitalInAcquisitionModeSet(FT_HANDLE handle,RDACQMODE acqmode);

RDAPI int RDDigitalInTriggerSourceSet(FT_HANDLE handle,RDTRIGSRC trigsrc);//RDDigitalInBufferSizeSet
RDAPI int RDDigitalInTriggerTypeSet(FT_HANDLE handle, RDTRIGTYPE type);//type=0 for slope 1 for future
RDAPI int RDDigitalInTriggerSlopeSet(FT_HANDLE handle,RDTriggerSlope slope);
RDAPI int RDDigitalInTriggerSet(FT_HANDLE handle,uint Rais,uint Fall);
RDAPI int RDDigitalInTriggerTimeoutSet(FT_HANDLE handle, int enable);

//    int  RDDigitalInTriggerPositionSet(FT_HANDLE handle,int cSamplesAfterTrigger);
//    int  RDDigitalInTriggerPrefillSet(FT_HANDLE handle,int cSamplesBeforeTrigger);
//    int  RDDigitalInTriggerAutoTimeoutSet(FT_HANDLE handle,int secTimeout);
//    int  RDDigitalInTriggerSet(FT_HANDLE handle,int fsLevelLow,int fsLevelHigh,int fsEdgeRise,int fsEdgeFall);

//    int  RDDigitalInTriggerResetSet( FT_HANDLE handle,int fsLevelLow,int fsLevelHigh,int fsEdgeRise,int fsEdgeFall);
//    int  RDDigitalInTriggerCountSet( FT_HANDLE handle, int cCount, int fRestart);
//    int  RDDigitalInTriggerLengthSet( FT_HANDLE handle, int secMin,int secMax,int idxSync);
//    int  RDDigitalInTriggerMatchSet( FT_HANDLE handle,int iPin, int fsMask,int fsValue, int cBitStuffing);
RDAPI int  RDDigitalIOOutputEnableSet(FT_HANDLE handle,uint outputs);
RDAPI int  RDDigitalIOOutputSet(FT_HANDLE handle,uint sets);
RDAPI int  RDDigitalIOInputStatus(FT_HANDLE handle,uint* reads);
RDAPI int  RDDigitalInConfigure(FT_HANDLE handle,bool enable);
RDAPI int  RDDigitalInStatus(FT_HANDLE handle,RDState* sts);
RDAPI int  RDDigitalInRead(FT_HANDLE handle,int size,uint16_t* RxBuffer,int *backsize);

//RDAPI int RDDigitalOutReset(FT_HANDLE handle);
RDAPI int RDDigitalOutRun(FT_HANDLE handle,bool enable);//run
//RDDigitalOutStatus(FT_HANDLE handle, DwfState *psts);

    // Configuration:
RDAPI int RDDigitalOutTriggerSourceSet(FT_HANDLE handle, RDTRIGSRC trigsrc);
//RDDigitalOutRunSet(FT_HANDLE handle, m_patternconfig.secRun);
//RDDigitalOutWaitSet(FT_HANDLE handle, m_patternconfig.secWait);
//RDDigitalOutRepeatSet(FT_HANDLE handle, m_patternconfig.cRepeat);
RDAPI int RDDigitalOutTriggerSlopeSet(FT_HANDLE handle, RDTriggerSlope slope);
//RDAPI int RDDigitalOutRepeatTriggerSet(FT_HANDLE handle,m_patternconfig.fRepeatTrigger);
//RDAPI int RDDigitalOutCount(FT_HANDLE handle, &m_patternconfig.pcChannel);
RDAPI int RDDigitalOutEnableSet(FT_HANDLE handle, uint chs);
    //RDDigitalOutOutputSet(FT_HANDLE handle,i, m_patternconfig.output.at(i));
RDAPI int RDDigitalOutTypeSet(FT_HANDLE handle,int ch,RDDigitalOutType type);
RDAPI int RDDigitalOutIdleSet(FT_HANDLE handle,int ch, RDDigitalOutIdle idle);
RDAPI int RDDigitalOutDividerInitSet(FT_HANDLE handle,int ch, uint divinit);
RDAPI int RDDigitalOutDividerSet(FT_HANDLE handle,int ch, uint div);
RDAPI int RDDigitalOutCounterInitSet(FT_HANDLE handle,int ch,int initlevel,uint counter); //1 counter=25ns
RDAPI int RDDigitalOutCounterSet(FT_HANDLE handle,int ch,  uint counter_l,uint counter_h);
//RDAPI int RDDigitalOutDataSet(FT_HANDLE handle,int ch, uchar* rgdSamples ,uint countOfBits);
RDAPI int RDDigitalOutPWMDirectSet(FT_HANDLE handle, int direct);
RDAPI int RDDigitalOutPWMValueSet(FT_HANDLE handle, int Counts[4]);
RDAPI int RDDigitalOutPWMRun(FT_HANDLE handle, bool enable);

RDAPI int RDDigitalUartRateSet(FT_HANDLE handle, double rate); // 9.6kHz
RDAPI int RDDigitalUartTxRxIOSet(FT_HANDLE handle, int TxDIO, int RxDIO); // RX = DIO-0
RDAPI int RDDigitalUartBitsSet(FT_HANDLE handle, int bits); // 8 bits
RDAPI int RDDigitalUartParitySet(FT_HANDLE handle, int parity); // 0 none, 1 odd, 2 even
RDAPI int RDDigitalUartStopSet(FT_HANDLE handle, double stop); // 1 bit stop length
RDAPI int RDDigitalUartTx(FT_HANDLE handle, uchar* data, int length);
RDAPI int RDDigitalUartRx(FT_HANDLE handle, uchar* rgRX, int length, int * rxcount, int *fParity);
RDAPI int RDDigitalI2CRateSet(FT_HANDLE handle, double rate); //
RDAPI int RDDigitalI2CTxRxIOSet(FT_HANDLE handle, int SCLDIO, int SDADIO); // SCLDIO = DIO-0
RDAPI int RDDigitalI2CTx(FT_HANDLE handle,uchar addr, uchar* data, int length);
RDAPI int RDDigitalI2CRx(FT_HANDLE handle,uchar addr, uchar* rgRX, int length, int * rxcount, int *fParity);

RDAPI int RDDigitalSPISlaveSet(FT_HANDLE handle, int slave);
RDAPI int RDDigitalSPIModeSet(FT_HANDLE handle, int mode);
RDAPI int RDDigitalSPIRateSet(FT_HANDLE handle, double rate); //
RDAPI int RDDigitalSPITxRxIOSet(FT_HANDLE handle, int CSDIO,int ClockDIO,int DQ0, int DQ1); // RX = DIO-0
RDAPI int RDDigitalSPIDelaySet(FT_HANDLE handle, int delayCLK);
RDAPI int RDDigitalSPITx(FT_HANDLE handle, uchar* data, int length);
RDAPI int RDDigitalSPIRx(FT_HANDLE handle, uchar* rgRX, int length, int * rxcount, int *fParity);

RDAPI int RDSPISPECIALSwitch(FT_HANDLE handle, bool enable);
RDAPI int RDSPISPECIALPluseSwitch(FT_HANDLE handle, bool enable);
RDAPI int RDSPISPECIALIOSwitch(FT_HANDLE handle, int state);

RDAPI int RDSPISPECIALRead(FT_HANDLE handle, uchar* rgRX,int * rxcount,int miniblock=30);//rgRX length need bigger than 16384



RDAPI int RDwrite(FT_HANDLE handle, uchar *data, int count);
RDAPI int RDread(FT_HANDLE handle, uchar *data, int *count, int msTimeout=0);

RDAPI int RDFlushData(FT_HANDLE handle);

RDAPI int setDevice(int ver,double password);
RDAPI int readDeviceInfo();
///-------------DMM---------------------------------------------------------------------------///

//sqlite
struct CalibrationData {
    std::string SN;
    std::string Type;
    std::string Range;
    double K;
    double B;
    double Offset;
};
std::vector<CalibrationData> dmmcalibrationdata;
std::vector<CalibrationData> getDMMCalibrationData(const std::string& sn, const std::string& tableName);

RDAPI char* RDgetDmmCalibrationDataToString();
struct DMMConfig
{
   int type=0;
   int range=0;
   int lowrangeonce=0;
   int dmmtype=0;
   double k,b,offset,rangevalue,scale;
   std::string unit;
}m_dmmconfig;

RDAPI int RDDMMOpen(FT_HANDLE fthandle,bool OpenT);//0 open success 1 close success 2 iic openfailed 3 calibrationdata read failed
RDAPI int RDDMMSet(FT_HANDLE fthandle,RDDMMType type,int indexOfrange);
RDAPI int RDDMMReadSingle(FT_HANDLE fthandle,char* data,int *backsize);

int DMMIICSet(FT_HANDLE fthandle,char* type,int indexOfrange);
int DMMSPISet(FT_HANDLE fthandle,char* type,int indexOfrange);
char* DMMIICReadSingle(FT_HANDLE fthandle,uchar* bzTx=new uchar[3]{0x60,0x60,0x00},int nTx=2,int nRx=5,int *backsize=nullptr);
char* DMMSPIReadSingle(FT_HANDLE fthandle,int *backsize=nullptr);

int RDDMMSPIWRSet(FT_HANDLE handle, int WR);//aaff050504 dmm_spi+00+00/01 W/R
int RDDMMSPISwitchSet(FT_HANDLE handle, int Switch);
int RDDMMSPIWrite(FT_HANDLE handle, uchar * data);//aaff050504 dmm_spi+01之后发送写的数据，固定两个字节，比如h40 hc0
int RDDMMSPIRead(FT_HANDLE handle, uchar * rgRX,int * rxcount);//aaff050504 dmm_spi+02读SPI收到的数据

std::string getUnit(const char* str) ;
double parseValue(const char* str) ;
///Ch4 Instruments' DMM PART
#define MSG_ERROR_SIZE      20

#define ERRVAL_SUCCESS                  0       // success

#define ERRVAL_EPROM_WRTIMEOUT          0xFF    // EPROM write data ready timeout
#define ERRVAL_EPROM_CRC                0xFE    // wrong CRC when reading data from EPROM
#define ERRVAL_EPROM_MAGICNO            0xFD    // wrong Magic No. when reading data from EPROM

#define ERRVAL_DMM_IDXCONFIG            0xFC    // wrong scale index
#define ERRVAL_CALIB_NANDOUBLE          0xFB    // not a number double value

#define ERRVAL_DMM_VALIDDATATIMEOUT     0xFA    // valid data DMM timeout
#define ERRVAL_CMD_WRONGPARAMS          0xF9    // wrong parameters when sending UART commands
#define ERRVAL_CMD_MISSINGCODE          0xF8    // the provided code is not among accepted values
#define ERRVAL_EPROM_VERIFY             0xF7    // eprom verify error
#define ERRVAL_EPROM_ADDR_VIOLATION     0xF6    // EPROM write address violation: attempt to write over system data
#define ERRVAL_DMM_CFGVERIFY            0xF5    // DMM Configuration verify error
#define ERRVAL_CMD_VALWRONGUNIT         0xF4    // The provided value has a wrong measure unit.
#define ERRVAL_CMD_VALFORMAT            0xF2    // The numeric value cannot be extracted from the provided string.
#define ERRVAL_DMM_MEASUREDISPERSION    0xF1    // The calibration measurement dispersion exceeds accepted range
#define ERRVAL_CALIB_MISSINGMEASUREMENT 0xF0    // A measurement must be performed before calling the finalize calibration.

#define DMM_DIODEOPENTHRESHOLD      3
//#define INFINITY        1e+308      // value used when the retrieved data exceeds the convertors range
//#define NAN             0.0f/0.0f   // value used when no proper data is available


#define DmmResistance               1
#define DmmContinuity               2
#define DmmDiode                    3
#define DmmDCVoltage                4
#define DmmACVoltage                5
#define DmmDCCurrent                6
#define DmmACCurrent                7
#define DmmDCLowCurrent             8
#define DmmACLowCurrent             9

#define DMM_CNTSCALES                 27    // the number of scales
#define DMM_VALIDDATA_CNTTIMEOUT    0x100   // number of valid data retrieval re-tries 0x100
#define DMMVoltageDC50Scale          7

#define DMM_Voltage50DCLinearCoeff_P3   -1.59128E-06
#define DMM_Voltage50DCLinearCoeff_P1   1.003918916
#define DMM_Voltage50DCLinearCoeff_P0   0.000196999


typedef struct _DMMCFG{
    int mode; // user modes
    double range;
    uchar sw;     // switch bits: 0 RLD, 1 RLU, 2 RLI
    uchar cfg[24]; // configuration bits: 0x1F...0x36
    double mul; // dmm measurement (ad1/rms) multiplication factor to get value in corresponding unit
} DMMCFG;

// registers from 0x00 to 0x1F
typedef struct _DMMSTS{
    uchar ad1[3];
    uchar ad2[3];
    uchar lpf[3];
    uchar rms[5];
    uchar pkhmin[3];
    uchar pkhmax[3];//20
    uchar ctsta;
    uchar ctc[3];
    uchar ctb[3];
    uchar cta[3];//30
    uchar intf;
    uchar inte;
} DMMSTS;


// calibration values

#define NO_CALIBS   10
typedef struct _CALIB{
    float  Mult;
    float  Add;
} CALIB;

typedef struct _PARTCALIB{
    double Calib_Ms_Zero;
    double Calib_Ms_ValP;
    double Calib_Ref_ValP;
    double Calib_Ms_ValN;
    double Calib_Ref_ValN;
    uchar fCalibDirty;
} PARTCALIB;


typedef struct _CALIBDATA{    //
    uchar magic;
    CALIB      Dmm[DMM_CNTSCALES];    // 27*2  54
    uchar crc;
}  CALIBDATA;//__attribute__((__packed__))


typedef struct _PARTCALIBDATA{    //
    PARTCALIB  DmmPartCalib[DMM_CNTSCALES];    // stores the data needed to the calibration
} PARTCALIBDATA;


double DMM_TmpDebugDGetStatus(uchar *pbErr, char *pString);
// DMM initialization
void DMM_Init();

// configuration functions
uchar DMM_SetScale(FT_HANDLE handle,int idxScale);
int DMM_GetCurrentScale();
double DMM_GetScaleRange(int idxScale);
int DMM_ConfigSwitches(FT_HANDLE handle,int sw);

// value functions
double DMM_DGetValue(FT_HANDLE handle,uchar *pbErr);
double DMM_DGetAvgValue(int cbSamples, uchar *pbErr);
void DMM_SetUseCalib(uchar f);
uchar DMM_CheckAcceptedMeasurementDispersion(double dMeasuredVal, double dRefVal, double *pDispersion);
uchar DMM_FormatValue(double dVal, char *pString, uchar fUnit);
uchar DMM_InterpretValue(char *pString, double *pdVal);

uchar DMM_FDCCurrentScale();


// DMM SPI functions
int DMM_SendCmdSPI(FT_HANDLE ftHandle,uchar bCmd, int bytesNumber, uchar *pbWrData);
int DMM_GetCmdSPI(FT_HANDLE ftHandle,uchar bCmd, int bytesNumber, uchar *pbRdData);

// retrieve value from DMM
double DMM_DGetStatus(FT_HANDLE ftHandle,uchar *pbErr);

// value format
uchar DMM_GetScaleUnit(int idxScale, double *pdScaleFact, char *szUnitPrefix, char *szUnit);

// configuration functions
uchar DMM_FACScale(int idxScale);
double DMM_CompensateVoltage50DCLinear(double dVal);
// errors
uchar DMM_ERR_CheckIdxCalib(int idxScale);

// utils
uchar DMM_IsNotANumber(double dVal);
uchar DMM_GetFormattedValue(FT_HANDLE handle,char *pString);

CALIBDATA calib; // defined in calib.c
#define CALIB_ACCEPTANCE_DEFAULT    0.2
// mask unused register bits on configuration verification
const uchar dmmcfgmask[24]={0x1F, 0xFE, 0xFF, 0xFF, 0x9F, 0xFF, 0xFF, 0xBF, 0xFF, 0x33, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xBC, 0xFC, 0xFF};

// configuration, contains scale specific data
const DMMCFG dmmcfg[28] = {
//                                 0,    1,    2,    3,    4,    5,    6,    7,    8,    9,   10,   11,   12,   13,   14,   15,   16,   17,   18,   19,   20,   21,   22,   23,
//                              INTE,  R20,  R21,  R22,  R23,  R24,  R25,  R26,  R27,  R28,  R29,  R2A,  R2B,  R2C,  R2D,  R2E,  R2F,  R30,  R31,  R32,  R33,  R34,  R35,  R36
{DmmResistance, 5e7,     1, {0x00, 0xC0, 0xCF, 0x17, 0x93, 0x85, 0x00, 0x00, 0x55, 0x55, 0x00, 0x00, 0x08, 0x00, 0x00, 0x80, 0x86, 0x80, 0xD1, 0x3C, 0xA0, 0x00, 0x00, 0x00}, 6e7 /0.9/8388608      }, // 0 "50M Ohm"
{DmmResistance, 5e6,     1, {0x00, 0xC0, 0xCF, 0x17, 0x93, 0x85, 0x00, 0x00, 0x55, 0x55, 0x00, 0x00, 0x08, 0x00, 0x80, 0x80, 0x86, 0x80, 0xD1, 0x3C, 0xA0, 0x00, 0x00, 0x00}, 6e6 /0.9/8388608      }, // 1 "5M Ohm"
{DmmResistance, 5e5,     1, {0x00, 0xC0, 0xCF, 0x17, 0x93, 0x85, 0x00, 0x00, 0x55, 0x55, 0x00, 0x00, 0x08, 0x00, 0x08, 0x80, 0x86, 0x80, 0xD1, 0x33, 0x20, 0x00, 0x00, 0x00}, 6e5 /0.9/8388608      }, // 2 "500k Ohm"
{DmmResistance, 5e4,     1, {0x00, 0xC0, 0xCF, 0x17, 0x83, 0x85, 0x00, 0x00, 0x55, 0x00, 0x00, 0x00, 0x40, 0x00, 0x06, 0x44, 0x94, 0x80, 0xD3, 0x33, 0x20, 0x00, 0x00, 0x00}, 1e5 /0.9/8388608      }, // 3 "50k Ohm"
{DmmResistance, 5e3,     1, {0x00, 0xC0, 0xCF, 0x17, 0x83, 0x85, 0x00, 0x00, 0x55, 0x00, 0x00, 0x00, 0x40, 0x60, 0x00, 0x44, 0x94, 0x80, 0xD3, 0x33, 0x20, 0x00, 0x00, 0x00}, 1e4 /0.9/8388608      }, // 4 "5k Ohm"
{DmmResistance, 5e2,     1, {0x00, 0xC0, 0xCF, 0x17, 0x83, 0x35, 0x00, 0x00, 0x55, 0x00, 0x00, 0x00, 0x40, 0x06, 0x00, 0x44, 0x94, 0x80, 0xD2, 0x3C, 0xA0, 0x00, 0x00, 0x00}, 1e3 /0.9/8388608      }, // 5 "500 Ohm"
{DmmResistance, 5e1,     1, {0x00, 0xC0, 0xCF, 0x17, 0x83, 0x35, 0x01, 0x00, 0x55, 0x00, 0x00, 0x00, 0x40, 0x06, 0x00, 0x44, 0x94, 0x80, 0xD2, 0x3C, 0xA0, 0x00, 0x00, 0x00}, 1e2 /0.9/8388608      }, // 6 "50 Ohm"
{DmmDCVoltage, 5e1,      2, {0x00, 0x60, 0x00, 0x17, 0x8B, 0x01, 0x11, 0x00, 0x55, 0x31, 0x00, 0x22, 0x00, 0x00, 0x09, 0x28, 0xA0, 0x80, 0xC7, 0x33, 0x20, 0x00, 0x00, 0x00}, 125e0 /1.8/8388608    }, // 7 "50 V DC",
{DmmDCVoltage, 5e0,      2, {0x00, 0x60, 0x00, 0x17, 0x8B, 0x01, 0x11, 0x00, 0x55, 0x31, 0x00, 0x22, 0x00, 0x00, 0x90, 0x28, 0xA0, 0x80, 0xC7, 0x33, 0x20, 0x00, 0x00, 0x00}, 125e-1/1.8/8388608    }, //8 "5 V DC",
{DmmDCVoltage, 5e-1,     1, {0x00, 0xC0, 0x00, 0x17, 0x8B, 0x85, 0x11, 0x00, 0x55, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x90, 0x80, 0xC7, 0x33, 0x28, 0x00, 0x00, 0x00}, 125e-2/1.8/8388608    }, //9 "500 mV DC"
{DmmDCVoltage, 5e-2,     1, {0x00, 0x00, 0x00, 0x17, 0x8B, 0x35, 0x11, 0x00, 0x55, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x90, 0x80, 0xC7, 0x3C, 0x60, 0x00, 0x00, 0x00}, 125e-3/1.8/8388608    }, //10 "50 mV DC"
{DmmACVoltage, 5e1,      2, {0x00, 0xF2, 0xDD, 0x07, 0x03, 0x52, 0x10, 0x80, 0x25, 0x31, 0xF8, 0x22, 0x00, 0x00, 0x0D, 0x28, 0xA0, 0xFF, 0xC7, 0x38, 0x20, 0x00, 0x00, 0x00}, 1e-3                  }, //11 "30 V AC"
{DmmACVoltage, 5e0,      2, {0x00, 0xF2, 0xDD, 0x07, 0x03, 0x52, 0x10, 0x80, 0x25, 0x31, 0xF8, 0x22, 0x00, 0x00, 0xD0, 0x88, 0xA0, 0xFF, 0xC7, 0x38, 0x20, 0x02, 0x50, 0x0C}, 1e-4                  }, //12 "5 V AC"
{DmmACVoltage, 5e-1,     1, {0x00, 0x92, 0xDD, 0x07, 0x03, 0x52, 0x10, 0x80, 0x25, 0x11, 0xF8, 0x00, 0x00, 0x00, 0x00, 0x00, 0x90, 0x80, 0xC7, 0x3A, 0x28, 0x00, 0x00, 0x00}, 1e-5                  }, //13 "500 mV AC"
{DmmACVoltage, 5e-2,     1, {0x00, 0x52, 0xDD, 0x07, 0x03, 0x00, 0x13, 0x80, 0x25, 0x11, 0xF8, 0x00, 0x00, 0x00, 0x00, 0x00, 0x90, 0x80, 0xC7, 0x3A, 0x28, 0x00, 0x00, 0x00}, 1e-6                  }, //14 "50 mV AC"
{DmmDCCurrent, 5e0,      0, {0x00, 0x00, 0x00, 0x17, 0x8B, 0x95, 0x11, 0x00, 0x55, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80, 0x80, 0xC7, 0x33, 0x20, 0x00, 0x00, 0x00}, 125e0/3.6/8388608     }, //15 "5 A DC" 125e0/3.6/8388608
{DmmACCurrent, 5e0,      0, {0x00, 0x52, 0xDD, 0x07, 0x03, 0x00, 0x13, 0x80, 0x25, 0x11, 0xF8, 0x00, 0x00, 0x00, 0x00, 0x00, 0x90, 0x80, 0xC7, 0x3D, 0x28, 0x00, 0x00, 0x00}, 1e-4/2.16             }, //16 "5 A AC"
{DmmContinuity,500,      1, {0x00, 0x74, 0xCF, 0x17, 0x83, 0x35, 0x10, 0x00, 0x55, 0x00, 0x00, 0x00, 0x00, 0x0A, 0x00, 0x40, 0x86, 0x80, 0xD2, 0x3C, 0xA0, 0x00, 0x00, 0x00}, 666e-7                }, //17 "Continuity
{DmmDiode,     3.0,      1, {0x00, 0xC0, 0xCF, 0x17, 0x8B, 0x8D, 0x10, 0x00, 0x55, 0x31, 0x00, 0x00, 0x00, 0x08, 0x00, 0x40, 0x86, 0x80, 0xE2, 0x33, 0xA0, 0x00, 0x00, 0x00}, 666e-6                }, //18 "Diode
{DmmDCLowCurrent, 5e-1,  0, {0x00, 0x00, 0x00, 0x17, 0x8B, 0x95, 0x11, 0x00, 0x55, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80, 0x80, 0xC7, 0x33, 0x20, 0x00, 0x00, 0x00}, 125e-2/1.8/8388608    }, //19 "500 mA DC"
{DmmDCLowCurrent, 5e-2,  0, {0x00, 0x00, 0x00, 0x17, 0x8B, 0x35, 0x11, 0x00, 0x55, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80, 0x80, 0xC7, 0x3D, 0xA0, 0x00, 0x00, 0x00}, 125e-3/1.8/8388608    }, //20 "50 mA DC"
{DmmDCLowCurrent, 5e-3,  4, {0x00, 0x00, 0x00, 0x17, 0x8B, 0x95, 0x11, 0x00, 0x55, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80, 0x80, 0xC7, 0x33, 0x20, 0x00, 0x00, 0x00}, 125e-4/1.8/8388608    }, //21 "5 mA DC"
{DmmDCLowCurrent, 5e-4,  4, {0x00, 0x00, 0x00, 0x17, 0x8B, 0x35, 0x11, 0x00, 0x55, 0x31, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80, 0x80, 0xC7, 0x3D, 0xA0, 0x00, 0x00, 0x00}, 125e-5/1.8/8388608    }, //22 "500 uA DC"
{DmmACLowCurrent, 5e-1,  0, {0x00, 0x92, 0xDD, 0x07, 0x03, 0x52, 0x10, 0x80, 0x25, 0x11, 0xF8, 0x00, 0x00, 0x00, 0x00, 0x00, 0x90, 0x80, 0xC7, 0x3D, 0x28, 0x00, 0x00, 0x00}, 1e-5/1.08             }, //23 "500 mA AC"
{DmmACLowCurrent, 5e-2,  0, {0x00, 0x52, 0xDD, 0x07, 0x03, 0x00, 0x13, 0x80, 0x25, 0x11, 0xF8, 0x00, 0x00, 0x00, 0x00, 0x00, 0x90, 0x80, 0xC7, 0x3D, 0x28, 0x00, 0x00, 0x00}, 1e-6/1.08             }, //24 "50 mA AC"
{DmmACLowCurrent, 5e-3,  4, {0x00, 0x92, 0xDD, 0x07, 0x03, 0x52, 0x10, 0x80, 0x25, 0x11, 0xF8, 0x00, 0x00, 0x00, 0x00, 0x00, 0x90, 0x80, 0xC7, 0x3D, 0x28, 0x00, 0x00, 0x00}, 1e-7/1.08             }, //25 "5 mA AC"
{DmmACLowCurrent, 5e-4,  4, {0x00, 0x52, 0xDD, 0x07, 0x03, 0x00, 0x13, 0x80, 0x25, 0x11, 0xF8, 0x00, 0x00, 0x00, 0x00, 0x00, 0x90, 0x80, 0xC7, 0x3D, 0x28, 0x00, 0x00, 0x00}, 1e-8/1.08             }, //26 "500 uA AC"
{0}};
DMMCFG curCfg;
int idxCurrentScale = -1;   // stores the current selected scale
char fUseCalib = 0;         // controls if calibration coefficients should be applied in DMM_DGetStatus



#endif // INSTRUMENTSPLAYGROUND_H
