#!/usr/bin/env python
# Modules import
import rospy
import serial
import time
import sys

from autopilots.msg import StateMachine
from sensor_msgs.msg import *

class Telecom():
	def __init__(self, quadN):
		self.quadN 		= quadN
		self.ns			= '/Quad'+str(quadN)
		self.port		= '/dev/ttyUSB1'
		self.baudrate		= 57600
		self.ser		= serial.Serial()
		self.out_buf		= None
		self.in_buf		= None

		# my gps
		self.my_gps_msg	= NavSatFix()
		self.my_lat		= 0.0
		self.my_lon		= 0.0	

		# my state machine state
		self.my_sm_msg		= StateMachine()

		# resolve other quads' namespaces
		if (quadN == 1):
			self.quadA_N 	= 2
			self.quadB_N 	= 3
			self.quadA_ns 	= '/Quad2'
			self.quadB_ns 	= '/Quad3'
		elif (quadN == 2):
			self.quadA_N 	= 1
			self.quadB_N 	= 3
			self.quadA_ns 	= '/Quad1'
			self.quadB_ns 	= '/Quad3'
		elif (quadN == 3):
			self.quadA_N 	= 1
			self.quadB_N 	= 2
			self.quadA_ns 	= '/Quad1'
			self.quadB_ns 	= '/Quad2'
		else:
			rospy.logerr('Quad ID is not 1, 2, or 3')
			exit(1)

		# other quad A
		# gps
		self.quadA_gps_msg 	= NavSatFix()
		self.quadA_lat		= 0.0
		self.quadA_lon		= 0.0
		# state machine
		self.quadA_sm_msg 	= StateMachine()

		# other quad B
		self.quadB_gps_msg 	= NavSatFix()
		self.quadB_lat		= 0.0
		self.quadB_lon		= 0.0
		# state machine
		self.quadB_sm_msg 	= StateMachine()

		# subscribers
		# to my gps
		rospy.Subscriber(self.ns+'/mavros/global_position/global', NavSatFix, self.gps_cb)
		# to my state machine state
		rospy.Subscriber(self.ns+'/state_machine/state', StateMachine, self.sm_cb)

		# publishers
		# quadA
		self.qA_gps_pub 	= rospy.Publisher(self.quadA_ns + '/mavros/global_position/global',NavSatFix, queue_size=10)
		self.qA_state_pub 	= rospy.Publisher(self.quadA_ns + '/state_machine/state', StateMachine, queue_size=10)
		# quadB
		self.qB_gps_pub 	= rospy.Publisher(self.quadB_ns + '/mavros/global_position/global',NavSatFix, queue_size=10)
		self.qB_state_pub 	= rospy.Publisher(self.quadB_ns + '/state_machine/state', StateMachine, queue_size=10)

		# counter for transmission
		self.counter 		= 0

		# receoption counter
		# quadA
		self.qA_gps_c		= 0
		self.qA_sm_c		= 0
		# quadB
		self.qB_gps_c		= 0
		self.qB_sm_c		= 0
		
		# test counter
		self.test_c		= 0

		# DATA packet length (elements)
		self.DATA_LENGTH	= 10


	# callbacks
	def gps_cb(self, msg):
		if msg is not None:
			self.my_gps_msg = msg
	
	def sm_cb(self, msg):
		if msg is not None:
			self.my_sm_msg = msg

	# open serial
	def open_serial(self):
		self.ser.timeout	= 0
		self.ser.bytesize	= serial.EIGHTBITS
		self.ser.parity		= serial.PARITY_NONE
		self.ser.stopbits	= serial.STOPBITS_ONE
		self.ser.port		= self.port
		self.ser.baudrate	= self.baudrate		
		self.ser.open()

	# encoding function
	def encode(self):
		if self.ser.isOpen():
			self.out_buf = ''
			self.out_buf 	= 'Q'+ ',' + str(self.quadN) + ',' + 'gps' + ',' + str(self.my_gps_msg.header.seq) + ',' + str(self.my_gps_msg.latitude) + ',' + str(self.my_gps_msg.longitude)+ ',' + str(self.my_gps_msg.altitude)+ ',' +  'sm'+ ',' + str(self.my_sm_msg.header.seq) + ',' +  self.my_sm_msg.state+','
			# send buffer
			if self.my_gps_msg.header.seq > self.counter or self.my_sm_msg.header.seq > self.counter :
				self.ser.write(bytearray(self.out_buf))
				self.counter = max(self.my_gps_msg.header.seq, self.my_sm_msg.header.seq)
				self.ser.flushOutput()

			#else:
				#rospy.logwarn('Nothing to write to telemetry module.')
		else:
			rospy.logwarn('Telemetry serial port is not open.')

	def decode(self):
		res = False
		q= None
		gps_a = False
		sm_a = False
		gps_b = False
		sm_b = False
		if self.ser.isOpen():
			Nbytes = self.ser.inWaiting()
			if Nbytes > 0:
				self.in_buf = self.ser.read(Nbytes)
				self.ser.flushInput()
				# split string ','
				split = self.in_buf.split(',')
				L = len(split)
				# loop over the split string's elements
				for i in range(0,L-1):
					if split[i] == 'Q' :
						msg = split[i:i+self.DATA_LENGTH]
						if len(msg) == 10:
							# check quad number
							qn = msg[1]
							if qn == str(self.quadN):
								rospy.logerr('Quad ID is not unique!')
								exit(1)
							# start parsing
							# other quad A
							elif qn == str(self.quadA_N):
								try:
									self.quadA_gps_msg.header.stamp = rospy.Time.now()
									self.quadA_gps_msg.latitude = float(msg[4])
									self.quadA_gps_msg.longitude = float(msg[5])
									self.quadA_gps_msg.altitude = float(msg[6])
									self.quadA_sm_msg.header.stamp = rospy.Time.now()
									self.quadA_sm_msg.state = msg[9]	
									res =  True
									if int(msg[3]) > self.qA_gps_c:
										gps_a = True
										self.qA_gps_c = int(msg[3])
									if int(msg[8]) > self.qA_sm_c:
										sm_a = True
										self.qA_sm_c = int(msg[8])
								except:
									rospy.logwarn('corrupted message')
							# other quad B
							elif qn == str(self.quadB_N):
								try:
									self.quadB_gps_msg.header.stamp = rospy.Time.now()
									self.quadB_gps_msg.latitude = float(msg[4])
									self.quadB_gps_msg.longitude = float(msg[5])
									self.quadB_gps_msg.altitude = float(msg[6])
									self.quadB_sm_msg.header.stamp = rospy.Time.now()
									self.quadB_sm_msg.state = msg[9]
									res =  True
									if int(msg[3]) > self.qB_gps_c:
										gps_b = True
										self.qB_gps_c = int(msg[3])
									if int(msg[8]) > self.qB_sm_c:
										sm_b = True
										self.qB_sm_c = int(msg[8])
								except:
									rospy.logwarn('corrupted message')
							else:
								rospy.logerr('Quad ID is not 1,2, or 3.')
								exit(1)
						self.in_buf = []
						msg = []
		else:
			rospy.logwarn('Telemetry serial port is not open.')
		
		return res, gps_a, sm_a, gps_b, sm_b

	def test(self):
		if self.ser.isOpen():
			self.out_buf 	= self.out_buf 	= 'Q'+ ',' + str(self.quadN) + ',' + 'gps' + ',' + str(self.test_c) + ',' + str(39.23456789) + ',' + str(26.123456789)+ ',' + str(-17.5)+ ',' +  'sm'+ ',' + str(self.test_c) + ',' +  'test_state'+','
			# send buffer
			self.ser.write(bytearray(self.out_buf))
			self.test_c = self.test_c + 1
			self.ser.flushOutput()


def main(arg):
	rospy.init_node('telemetry_node', anonymous=True)
	rate = rospy.Rate(10)

	if len(arg)<2:
		rospy.logerr('Insufficient input arguments')
		return
		

	quadN = int(arg[1])
	obj = Telecom(quadN)

	if len(arg)>2:
		obj.port = arg[2]
	else:
		obj.port = '/dev/ttyUSB0'
	obj.baudrate = 57600

	obj.open_serial()
	while not rospy.is_shutdown():

		# encode
		obj.encode()
		# decode
		res,gps_a, sm_a, gps_b, sm_b = obj.decode()

		# publish
		if res:
			if gps_a:
				obj.qA_gps_pub.publish(obj.quadA_gps_msg)
			if sm_a:
				obj.qA_state_pub.publish(obj.quadA_sm_msg)
			if gps_b:
				obj.qB_gps_pub.publish(obj.quadB_gps_msg)
			if sm_b:
				obj.qB_state_pub.publish(obj.quadB_sm_msg)

		rate.sleep()


if __name__ == '__main__':
    
    try:
        main(sys.argv)
    except rospy.ROSInterruptException:
        pass
