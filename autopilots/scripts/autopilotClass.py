import rospy
import numpy as np
import tf
import myLib

from math import *
from std_msgs.msg import *
from sensor_msgs.msg import *
from geometry_msgs.msg import *
from mavros_msgs.msg import *
from mavros_msgs.srv import *


#########
# Autopilot parameters
#########

def setParams():

    # ROS parameters for autopilot
    rospy.set_param('/autopilot/fbRate',20.0)        # feedback rate (hz)
    rospy.set_param('/autopilot/altStep',3.0)        # initial altitude step command
    rospy.set_param('/autopilot/camOffset',0.3)      # camera offset from ground

    # ROS parameters for kAltVel
    rospy.set_param('/kAltVel/gP',1.5)
    rospy.set_param('/kAltVel/gI',0.1)
    rospy.set_param('/kAltVel/vMaxU',1.0)
    rospy.set_param('/kAltVel/vMaxD',0.5)
    rospy.set_param('/kAltVel/teraN',3)

    # ROS parameters for kBodVel
    rospy.set_param('/kBodVel/gP',0.5)
    rospy.set_param('/kBodVel/gI',0.05)
    rospy.set_param('/kBodVel/vMax',5.0)
    rospy.set_param('/kBodVel/gPyaw',0.5)           # yaw proportional gain
    rospy.set_param('/kBodVel/yawOff',0.25)          # error to turn off yaw control (m)
    rospy.set_param('/kBodVel/yawCone',45.0)        # cone to use proportional control (deg)
    rospy.set_param('/kBodVel/yawTurnRate',15.0)    # constant turn rate outside cone (deg/s)
    rospy.set_param('/kBodVel/feedForward', False)   # use EKF to feedforward estimates


class autopilotClass:

    def __init__(self):
        # Publishers
        self.command = rospy.Publisher('/mavros/setpoint_raw/local', PositionTarget, queue_size=10)

        # Instantiate a setpoint
        self.setp = PositionTarget()
        self.setp.type_mask = int('010111000111', 2)
        
        self.altK = self.kAltVel()
        self.bodK = self.kBodVel()
        self.modes = self.fcuModes()
        self.rate = rospy.Rate(rospy.get_param('/autopilot/fbRate'))

    #########
    #
    # class kAltVel
    #   Altitude controller based on outer loop velocity commands to FCU
    #
    # Return:
    #   vzRef = reference velocity to FCU (m/s, positive upward)
    #
    # Subscriptions:
    #   rospy.Subscriber('/mavros/local_position/pose', PoseStamped, self.cbPos)
    #   rospy.Subscriber('/mavros/local_position/velocity', TwistStamped, self.cbVel)
    #   rospy.Subscriber('/mavros/state', State, self.cbFCUstate)
    #   rospy.Subscriber('/mavros/extended_state', ExtendedState, self.cbFCUexState)
    #
    # ROS parameters:
    #   /autopilot/fbRate = feedback sampling rate (Hz)
    #   /kAltVel/gP = proportional gain
    #   /kAltVel/gI = integral gain
    #   /kAltVel/vMaxU = maximum upward reference velocity (positive m/s)
    #   /kAltVel/vMaxD = maximum downward reference velocity (positive m/s)
    #
    # Fields:
    #   callback functions & subscriptions
    #   ezInt = integrated altitude error
    #   zSp = commanded altitude setpoint (m)
    #   z = current altitude from /mavros/local_position/pose (m)
    #   vz = current altitude velocity from /mavros/local_position/velocity (m/s)
    #   teraRanges = vector of teraRanger measurements
    #   teraAgree = teraRange 0,1,2 agreement
    #   engaged = Boolean if armed and offboard
    #   landed = Boolean if landed
    #
    #####

    class kAltVel:
        def __init__(self):

            self.ezInt = 0.0
            self.zSp = 0.0
            self.z = 0.0
            self.vz = 0.0
            self.teraRanges = [0.0]*rospy.get_param('/kAltVel/teraN')
            self.teraAgree = False
            self.engaged = False
            self.airborne = False
            self.subPos = rospy.Subscriber('/mavros/local_position/pose', PoseStamped, self.cbPos)
            self.subVel = rospy.Subscriber('/mavros/local_position/velocity', TwistStamped, self.cbVel)
            self.subFCUstate = rospy.Subscriber('/mavros/state', State, self.cbFCUstate)
            self.subFCUexState = rospy.Subscriber('/mavros/extended_state', ExtendedState, self.cbFCUexState)
            self.subTera = rospy.Subscriber('/scan', LaserScan, self.cbTera)

        def cbPos(self,msg):
            if not msg == None:
                self.z = msg.pose.position.z
                
        def cbVel(self,msg):
            if not msg == None:
                self.vz = msg.twist.linear.z

        def cbFCUstate(self,msg):
            self.engaged = False
            if not msg == None:
                if msg.armed and (msg.mode == 'OFFBOARD'):
                    self.engaged = True
                    
        def cbFCUexState(self,msg):
            if not msg == None:
                if msg.landed_state == 2:
                    self.airborne = True
                else:
                    self.airborne = False
                    
        def cbTera(self,msg):
            self.teraAgree = False
            if not msg == None:
                self.teraRanges = msg.ranges[0:(rospy.get_param('/kAltVel/teraN')-1)]
                var = max(self.teraRanges) - min(self.teraRanges)
                if var < 0.5:
                    self.teraAgree = True

        def controller(self):
        
            fbRate = rospy.get_param('/autopilot/fbRate')
            gP = rospy.get_param('/kAltVel/gP')
            gI = rospy.get_param('/kAltVel/gI')
            vMaxU = rospy.get_param('/kAltVel/vMaxU')
            vMaxD = rospy.get_param('/kAltVel/vMaxD')

            ez = self.zSp - self.z                              # altitude error

            vzRef = gP*ez + gI*self.ezInt                       # to be published

            if vzRef > vMaxU or vzRef < -vMaxD:                 # anti-windup
                vzRef = myLib.sat(vzRef,-vMaxD,vMaxU)
            else:
                if self.engaged:                                # if armed & offboard
                    self.ezInt = self.ezInt + ez/fbRate         # integrate

            return vzRef

    ###################################
    #
    # class kBodVel
    #   Body velocity controller based on outer loop velocity commands to FCU
    #
    # Return:
    #   vxCom,vyCom,yawRateCom = reference commands to FCU (m/s, local ENU coordinates)
    #
    # Subscriptions:
    #   rospy.Subscriber('/mavros/local_position/pose', PoseStamped, self.cbPos)
    #   rospy.Subscriber('/mavros/local_position/velocity', TwistStamped, self.cbVel)
    #   rospy.Subscriber('/mavros/state', State, self.cbFCUstate)
    #   
    # ROS parameters:
    #   /autopilot/fbRate = feedback sampling rate (Hz)
    #   /kBodVel/gP = proportional gain for velocity control
    #   /kBodVel/gI = integral gain for velocity control
    #   /kBodVel/vMax = maximum reference velocity (positive m/s)
    #   /kBodVel/gPyaw = proportional gain for yaw control
    #   /kBodVel/yawOff = radius to disable yaw control (m)
    #   /kBodVel/yawCone = cone angle to disable (x,y) velocity commands (deg)
    #   /kBodVel/yawTurnRate = constant yaw turn rate (deg/s)
    #   /kBodVel/feedForward = boolean EKF to estimate target velocity and feedforward to controller
    #
    # Fields:
    #   callback functions, subscriptions
    #   exInt = integrated error
    #   eyInt = integrated error
    #   xSp = commanded x setpoint (NED-h, m) NOTE: NED-h = NED projected to horizontal
    #   ySp = commanded y setpoint (NED-h, m)
    #   x = x of body frame origin in local ENU coordinates (m)
    #   y = y of body frame origin in local ENU coordinates (m)
    #   vx, vy = body frame velocities (m/s)
    #   yaw = yaw angle of relative (yaw,pitch,roll) in Local ENU -> Body NED
    #   engaged = Boolean if armed and offboard
    #
    #   ekf = subclass to estimate the velocity and orientation of the setpoint
    #       xhat = state estimate
    #       F = dynamics matrix
    #       H = observation matrix
    #       P = covariance matrix
    #       Q = process noise covariance
    #       R = measurementnoise covariance
    #
    #   ekfUpdate = update call of state estimate
    #
    #####

    class kBodVel:
        def __init__(self):

            self.exInt = 0.0
            self.eyInt = 0.0
            self.xSp = 0.0
            self.ySp = 0.0
            self.x = 0.0
            self.y = 0.0
            self.yaw = 0.0
            self.vx = 0.0
            self.vy = 0.0
            self.engaged = False

            self.subPos = rospy.Subscriber('/mavros/local_position/pose', PoseStamped, self.cbPos)
            self.subVel = rospy.Subscriber('/mavros/local_position/velocity', TwistStamped, self.cbVel)
            self.subFCUstate = rospy.Subscriber('/mavros/state', State, self.cbFCUstate)

            self.ekf = self.EKF()
            
        class EKF:
            def __init__(self):
                self.xhat = np.matrix(np.zeros( (5,1) ))
                self.F = np.matrix(np.identity(5))
                self.H = np.matrix(np.zeros( (2,5) ))
                self.H[0,0] = 1.0
                self.H[1,1] = 1.0
                self.P = np.matrix(np.identity(5))
                self.Q = np.matrix(np.zeros( (5,5) ))
                self.Q[0,0] = 0.1
                self.Q[1,1] = 0.1
                self.Q[2,2] = 0.1
                self.Q[3,3] = 0.5
                self.Q[4,4] = 0.5
                self.R = np.matrix(np.identity(2))*0.1
                

        def cbPos(self,msg):
            if not msg == None:
                q = (
                    msg.pose.orientation.x,
                    msg.pose.orientation.y,
                    msg.pose.orientation.z,
                    msg.pose.orientation.w)
                euler = tf.transformations.euler_from_quaternion(q, 'rzyx') #yaw/pitch/roll
                self.x = msg.pose.position.x
                self.y = msg.pose.position.y
                self.yaw = euler[0]
                
        def cbVel(self,msg):
            if not msg == None:
                self.vx = msg.twist.linear.x
                self.vy = msg.twist.linear.y

        def cbFCUstate(self,msg):
            if not msg == None:
                if msg.armed and (msg.mode == 'OFFBOARD'):
                    self.engaged = True
                else:
                    self.engaged = False
        
        def ekfUpdate(self,seeIt):
        
            fbRate = rospy.get_param('/autopilot/fbRate')
            h = 1/fbRate
                    
            # Update state estimate prior
            
            thHat = self.ekf.xhat[2]
            vHat = self.ekf.xhat[3]
            omegaHat = self.ekf.xhat[4]
            
            self.ekf.xhat[0] = self.ekf.xhat[0] + h*vHat*cos(thHat)
            self.ekf.xhat[1] = self.ekf.xhat[1] + h*vHat*sin(thHat)
            self.ekf.xhat[2] = self.ekf.xhat[2] + h*omegaHat
            
            # Update covariance prior
            self.ekf.F[0,2] = -vHat*sin(thHat)*h
            self.ekf.F[0,3] = cos(thHat)*h
            self.ekf.F[1,2] = vHat*cos(thHat)*h
            self.ekf.F[1,3] = sin(thHat)*h
            self.ekf.F[2,4] = h

            self.ekf.P = self.ekf.F*self.ekf.P*self.ekf.F.T + self.ekf.Q
            
            if seeIt:
                # Gather measurement and build residual
                e = np.matrix(np.zeros( (2,1) ) )
                bodyRot = self.yaw - pi/2.0                                 # rotation of NED y-axis
                e[0] =  (self.x - self.xSp*sin(bodyRot) + self.ySp*cos(bodyRot)) - self.ekf.xhat[0]    # local ENU x
                e[1] =  (self.y + self.xSp*cos(bodyRot) + self.ySp*sin(bodyRot)) - self.ekf.xhat[1]    # local ENU y
                
                # build ekf gain
                S = self.ekf.H*self.ekf.P*self.ekf.H.T + self.ekf.R
                K = self.ekf.P*self.ekf.H.T*S.I
                
                # update state estimate posterior 
                self.ekf.xhat = self.ekf.xhat + K*e
                
                # update covariance posterior
                Mtemp = np.matrix(np.identity(5)) - K*self.ekf.H
                self.ekf.P = Mtemp*self.ekf.P*Mtemp.T + K*self.ekf.R*K.T

        def controller(self):
        
            fbRate = rospy.get_param('/autopilot/fbRate')
            gP = rospy.get_param('/kBodVel/gP')
            gI = rospy.get_param('/kBodVel/gI')
            vMax = rospy.get_param('/kBodVel/vMax')
            gPyaw = rospy.get_param('/kBodVel/gPyaw')
            yawOff = rospy.get_param('/kBodVel/yawOff')
            yawCone = rospy.get_param('/kBodVel/yawCone')
            yawTurnRate = rospy.get_param('/kBodVel/yawTurnRate')
            feedForward = rospy.get_param('/kBodVel/feedForward')

            ######
            # longitudinal/lateral control
            ######
            
            ex = self.xSp                               # longitudinal error 
            vxRef = gP*ex + gI*self.exInt               # to be published
            
            ey = self.ySp                               # lateral error 
            vyRef = gP*ey + gI*self.eyInt               # to be published
            
            
            ######
            # Feedforward estimated velocities
            ######

            bodyRot = self.yaw - pi/2.0                        # rotation of NED y-axis
            if feedForward:
                thHat = self.ekf.xhat[2]
                vHat =  self.ekf.xhat[3]
                wHat = self.ekf.xhat[4]
                
                VX = vHat*cos(thHat)      # ENU coordinates                  
                VY = vHat*sin(thHat)
                
                #### vxRef = vxRef - VX*sin(thHat) + VY*cos(thHat) # convert estimates to body coordinates
                #### vyRef = vyRef + VX*cos(thHat) + VY*sin(thHat)
                
                vxRef = vxRef - VX*sin(bodyRot) + VY*cos(bodyRot) # convert estimates to body coordinates
                vyRef = vyRef + VX*cos(bodyRot) + VY*sin(bodyRot)

            vel = sqrt(vxRef**2 + vyRef**2)
            if vel > vMax:                            # anti-windup scaling      
                scale = vMax/vel
                vxRef = vxRef*scale
                vyRef = vyRef*scale
            else:
                if self.engaged:                            # if armed & offboard
                    self.exInt = self.exInt + ex/fbRate     # integrate
                    self.eyInt = self.eyInt + ey/fbRate

            ######
            # Convert body commands to local ENU coordinates
            ######

            vxCom = vyRef*cos(bodyRot) - vxRef*sin(bodyRot)    # local ENU velocity commands
            vyCom = vyRef*sin(bodyRot) + vxRef*cos(bodyRot)
            
            ######
            # Yaw control
            ######

            dYawSp = -atan2(vyRef,vxRef)                            # desired rotational change

            radius = sqrt(ex**2 + ey**2)
            if radius < yawOff:                                     # no yaw control if too close
                yaw_r = 0.0
            else:
                if abs(dYawSp) > radians(yawCone):                  # target out of view
                    yaw_r = copysign(radians(yawTurnRate),dYawSp)   # constant rate
                else:
                    yaw_r = gPyaw*dYawSp                            # proportional rate

            yawRateCom = yaw_r                                      # yaw rate command
                
            return vxCom, vyCom, yawRateCom


    ###################################
    #
    # function wayHome
    #   Vector to ENU home position expressed in NED body coordinates
    #
    # Syntax:
    #   vec2home_x, vec2home_y = wayHome(pos,home)
    #
    #   vec2home.x, vec2home.y = vector to home position expressed in body NED-h coordinates
    #   pos.x, pos.y, pos.yaw = origin & y-axis heading of NED body in local ENU coordinates
    #   home.x, home.y = location of home in local ENU coordinates
    #
    #####

    def wayHome(self,pos,home):
        dx = -(pos.x - home.x)
        dy = -(pos.y - home.y)
        
        bodyRot = pos.yaw - pi/2.0           # rotation of NED frame (ccw = positive)
        
        vec2home_x = dy*cos(bodyRot) - dx*sin(bodyRot)
        vec2home_y = dy*sin(bodyRot) + dx*cos(bodyRot)
        
        return vec2home_x, vec2home_y


    ###################################
    #
    # class xyzVar
    #   Generic class to subscribe to setpoints
    #
    # Subscriptions:
    #   
    #   rospy.Subscriber('xyzTopic', Point32, self.cbXYZ)
    #
    # Fields:
    #   x,y = target position
    #   z = detection flag -1/+1
    #
    #####

    class xyzVar:
        def __init__(self):
            self.x = 0.0
            self.y = 0.0
            self.z = 0.0
            
        def cbXYZ(self,msg):
            if not msg == None:
                self.x = msg.x
                self.y = msg.y
                self.z = msg.z


    ###################################
    #
    # class fcuModes
    #   Collection of service calls to arm/disarm/change modes
    #
    # Fields:
    #   setArm()
    #   setDisarm()
    #   setStabilzedMode()
    #   setOffboardMode()
    #   setAltitudeMode()
    #   setPositionMode()
    #   setAutoLandMode()
    #
    #####

    class fcuModes:

        def setArm(self):
            rospy.wait_for_service('/mavros/cmd/arming')
            try:
                armService = rospy.ServiceProxy('/mavros/cmd/arming', mavros_msgs.srv.CommandBool)
                armService(True)
            except rospy.ServiceException, e:
                print "Service arming call failed: %s"%e

        def setDisarm(self):
            rospy.wait_for_service('/mavros/cmd/arming')
            try:
                armService = rospy.ServiceProxy('/mavros/cmd/arming', mavros_msgs.srv.CommandBool)
                armService(False)
            except rospy.ServiceException, e:
                print "Service disarming call failed: %s"%e

        def setStabilizedMode(self):
            rospy.wait_for_service('/mavros/set_mode')
            try:
                flightModeService = rospy.ServiceProxy('/mavros/set_mode', mavros_msgs.srv.SetMode)
                flightModeService(custom_mode='STABILIZED')
            except rospy.ServiceException, e:
                print "service set_mode call failed: %s. Stabilized Mode could not be set."%e

        def setOffboardMode(self):
            rospy.wait_for_service('/mavros/set_mode')
            try:
                flightModeService = rospy.ServiceProxy('/mavros/set_mode', mavros_msgs.srv.SetMode)
                flightModeService(custom_mode='OFFBOARD')
            except rospy.ServiceException, e:
                print "service set_mode call failed: %s. Offboard Mode could not be set."%e

        def setAltitudeMode(self):
            rospy.wait_for_service('/mavros/set_mode')
            try:
                flightModeService = rospy.ServiceProxy('/mavros/set_mode', mavros_msgs.srv.SetMode)
                flightModeService(custom_mode='ALTCTL')
            except rospy.ServiceException, e:
                print "service set_mode call failed: %s. Altitude Mode could not be set."%e

        def setPositionMode(self):
            rospy.wait_for_service('/mavros/set_mode')
            try:
                flightModeService = rospy.ServiceProxy('/mavros/set_mode', mavros_msgs.srv.SetMode)
                flightModeService(custom_mode='POSCTL')
            except rospy.ServiceException, e:
                print "service set_mode call failed: %s. Position Mode could not be set."%e

        def setAutoLandMode(self):
            rospy.wait_for_service('/mavros/set_mode')
            try:
                flightModeService = rospy.ServiceProxy('/mavros/set_mode', mavros_msgs.srv.SetMode)
                flightModeService(custom_mode='AUTO.LAND')
            except rospy.ServiceException, e:
                print "service set_mode call failed: %s. Autoland Mode could not be set."%e

 
