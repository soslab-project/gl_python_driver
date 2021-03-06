#-*- coding:utf-8 -*-

import sys
import time
import numpy as np

import serial
import serial_comm


PS1             = 0xC3
PS2             = 0x51
PS3             = 0xA1
PS4             = 0xF8
SM_SET          = 0
SM_GET          = 1
SM_STREAM       = 2
SM_ERROR        = 255
BI_PC2GL310     = 0x21
BI_GL3102PC     = 0x12
PE              = 0xC2


STATE_INIT      = 0
STATE_PS1       = 1
STATE_PS2       = 2
STATE_PS3       = 3
STATE_PS4       = 4
STATE_preDATA   = 5
STATE_PE        = 6
STATE_CS        = 7



class Gl(object):

    def connection_made(self, transport):
        """Called when reader thread is started"""
        self.transport = transport

    def data_received(self, data):
        """Called with snippets received from the serial port"""
        for a in data:
            self.add_packet_element(a)

    def connection_lost(self, exc):
        """\
        Called when the serial port is closed or the reader loop terminated
        otherwise.
        """
        self.transport = None
        if isinstance(exc, Exception):
            raise exc

    #############################################################
    #  Constructor and Deconstructor for GL Class
    #############################################################
    def __init__(self):

        self.recv_packet_clear()

        
    #############################################################
    #  Functions for Serial Comm
    #############################################################
    def flush(self):
        self.recv_packet = np.array([], dtype=np.uint8)
        self.recv_TL = 0
        self.recv_SM = 0
        self.recv_CAT0 = 0
        self.recv_CAT1 = 0
        self.recv_DTL = 0
        self.recv_data = np.array([], dtype=np.uint8)
                

    def cs_update(self, data):
        self.cs_ = self.cs_^ (data&0xff)

    def cs_get(self):
        return self.cs_&0xff

    def cs_clear(self):
        self.cs_ = 0


    def write(self, data):
        self.transport.write(bytes(bytearray([data])))
        self.cs_update(data)


    def write_PS(self):
        PS = np.array([PS1, PS2, PS3, PS4])
        for i in PS:
            self.write(i)


    def write_packet(self, PI, PL, SM, CAT0, CAT1, DTn):
        self.flush()
        self.cs_clear()

        self.write_PS()

        DTL = DTn.shape[0]

        TL = DTL + 14
        buff = TL&0xff
        self.write(buff)
        buff = (TL>>8)&0xff
        self.write(buff)

        self.write(PI)
        self.write(PL)
        self.write(SM)
        self.write(BI_PC2GL310)
        self.write(CAT0)
        self.write(CAT1)

        for i in range(DTL):
            self.write(DTn[i])

        self.write(PE)
        self.write(self.cs_get())


    def recv_packet_clear(self):
        self.cs_clear()
        self.recv_state = STATE_INIT
        self.flush()


    def check_PS(self, data):
        if self.recv_state==STATE_INIT:
            if data==PS1:
                self.recv_packet_clear()
                self.cs_update(data)
                self.recv_state = STATE_PS1
        elif self.recv_state==STATE_PS1:
            if data==PS2:
                self.cs_update(data)
                self.recv_state = STATE_PS2
            else:
                return False
        elif self.recv_state==STATE_PS2:
            if data==PS3:
                self.cs_update(data)
                self.recv_state = STATE_PS3
            else:
                return False
        elif self.recv_state==STATE_PS3:
            if data==PS4:
                self.cs_update(data)
                self.recv_state = STATE_PS4
            else:
                return False
        else:
            return True


    def add_packet_element(self, data):
        PS_result = self.check_PS(data)
        if PS_result==False:
            self.recv_packet_clear()
            if data==PS1:
                self.recv_state = STATE_PS1

        elif PS_result==True:
            if self.recv_state==STATE_PS4:
                self.cs_update(data)
                self.recv_packet = np.append(self.recv_packet, np.array([data], dtype=np.uint8))
                
                if self.recv_packet.shape[0]==6 and self.recv_packet[5]!=BI_GL3102PC:
                    packet = self.recv_packet
                    self.recv_packet_clear()
                    self.data_received(packet)


                if self.recv_packet.shape[0]==9:
                    self.recv_TL = self.recv_packet[0]&0xff
                    self.recv_TL = self.recv_TL | ((self.recv_packet[1]&0xff)<<8)

                    self.recv_SM = self.recv_packet[4]&0xff

                    self.recv_CAT0 = self.recv_packet[6]&0xff
                    self.recv_CAT1 = self.recv_packet[7]&0xff
                    
                    self.recv_DTL = self.recv_TL - 14


                if self.recv_DTL>0:
                    if self.recv_DTL>self.recv_data.shape[0]:
                        self.recv_data = np.append(self.recv_data, np.array([data], dtype=np.uint8))
                    else:
                        self.recv_state = STATE_preDATA
                    
                if self.recv_state==STATE_preDATA:
                    if data==PE:
                        self.recv_state = STATE_PE
                    else:
                        packet = self.recv_packet
                        self.recv_packet_clear()
                        self.data_received(packet)


            elif self.recv_state==STATE_PE:
                if data==self.cs_get():
                    self.save_data(self.recv_data, self.recv_SM, self.recv_CAT0, self.recv_CAT1)
                    self.recv_packet_clear()
                else:
                    packet = self.recv_packet
                    self.recv_packet_clear()
                    self.data_received(packet)



    def save_data(self, recv_data, SM, CAT0, CAT1):

        # GetSerialNum()
        if SM==SM_GET and CAT0==0x02 and CAT1==0x0A:
            self.serial_num = self.recv_data.tostring().decode()

        # ReadFrameData()
        elif SM==SM_STREAM and CAT0==0x01 and CAT1==0x02:
            self.lidar_data = self.recv_data





    #############################################################
    #  Read GL Conditions
    #############################################################
    def GetSerialNum(self):
        PI = 0
        PL = 1
        SM = SM_GET
        CAT0 = 0x02
        CAT1 = 0x0A

        self.serial_num = ''

        DTn = np.array([1])
        self.write_packet(PI, PL, SM, CAT0, CAT1, DTn)

        for i in range(50):
            
            if hasattr(self, 'serial_num') and len(self.serial_num)>0:
                return self.serial_num

            time.sleep(0.1)
    
        return '[ERROR] Serial Number is not received'

    
    def ReadFrameData(self):
        if hasattr(self, 'lidar_data'):
            data_size = self.lidar_data[0]
            data_size = data_size | ((self.lidar_data[1]&0xff)<<8)

            dist_array = np.zeros((data_size,1), dtype=float)
            pulse_array = np.zeros((data_size,1), dtype=float)
            angle_array = np.zeros((data_size,1), dtype=float)

            for i in range(data_size):
                distance = self.lidar_data[i*4+2]&0xff
                distance = distance | ((self.lidar_data[i*4+3]&0xff)<<8)

                pulse_width = self.lidar_data[i*4+4]&0xff
                pulse_width = pulse_width | ((self.lidar_data[i*4+5]&0xff)<<8)

                if distance>30000:
                    distance = 0.0
                    
                dist_array[i] = distance/1000.0
                pulse_array[i] = pulse_width
                angle_array[i] = i*180.0/(data_size-1)*3.141592/180.0

                
            return dist_array, pulse_array, angle_array

        return np.array([]), np.array([]), np.array([])


    #############################################################
    #  Set GL Conditions
    #############################################################
    def SetFrameDataEnable(self, framedata_enable):
        PI = 0
        PL = 1
        SM = SM_SET
        CAT0 = 0x1
        CAT1 = 0x3

        DTn = np.array([framedata_enable])
        self.write_packet(PI, PL, SM, CAT0, CAT1, DTn)



# main
if __name__ == '__main__':

    ser = serial.serial_for_url('/dev/ttyUSB0', baudrate=921600, timeout=1)
    with serial_comm.ReaderThread(ser, Gl) as serial_gl:
        serial_gl.SetFrameDataEnable(False)
        time.sleep(0.5)
        print('Serial Num : ' + serial_gl.GetSerialNum())
        serial_gl.SetFrameDataEnable(True)

        while True:
            distance, pulse_width, angle = serial_gl.ReadFrameData()

            time.sleep(0.025)

