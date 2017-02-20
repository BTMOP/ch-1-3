#!/usr/bin/env python

import rospy
import numpy as np
import tf
import time
import os

from math import *
from std_msgs.msg import *
from sensor_msgs.msg import *
from geometry_msgs.msg import *
from mavros_msgs.msg import *
from mavros_msgs.srv import *

import myLib
import autopilotClass
autopilotClass.setParams()

###################################

# Main loop

def ch1sm():
    rospy.init_node('autopilot', anonymous=True)

    ####
    # Attributes:
    # sm.bodK, sm.altK, sm.modes
    # sm.setp, sm.rate.
    ####    
    sm = autopilotClass.autopilotClass()
    
    Testing = rospy.get_param('/kAltVel/smartLandingSim')
    
    # Instantiate a tracker
    target = sm.xyzVar()
    rospy.Subscriber('/getLaunchpad/launchpad/xyMeters', Point32, target.cbXYZ)
    #rospy.Subscriber('/getColors/blue/xyMeters', Point32, target.cbXYZ)
    
    # Instantiate various generic xyz positions
    home = sm.xyzVar()
    takeoff = sm.xyzVar()
    base = sm.xyzVar()
    ekfState = Vector3()
            
    # Cycle to initialize local positions
    kc = 0.0
    while kc < 10: # cycle for subscribers to read local position
        sm.rate.sleep()
        kc = kc + 1
       
       
    # Define ground levels
    
    if Testing:
        sm.altK.distanceSensor = sm.altK.z
        
    zGround = sm.altK.z    
    zGroundDistanceSensor = sm.altK.distanceSensor
    zGroundTera = np.mean(sm.altK.teraRanges)
                          
    zHover = rospy.get_param('/autopilot/altStep')   # base hover altitude
    takeoff.x = sm.bodK.x
    takeoff.y = sm.bodK.y
    base.x = takeoff.x                               # local ENU coordinates
    base.y = takeoff.y
    
    # Initializations
    camOffset = rospy.get_param('/autopilot/camOffset')
    
    # Grab original parameter values
    feedForward = rospy.get_param('/kBodVel/feedForward')
    vMax = rospy.get_param('/kBodVel/vMax')
    vMaxU = rospy.get_param('/kAltVel/vMaxU')
    vMaxD = rospy.get_param('/kAltVel/vMaxD')

    #################################
    # MODES
    # Takeoff: Initial takeoff
    # GoToBase: Go to base location while scanning
    # TrackUp: Track target while maintaining altitude
    # TrackDown: Track target while descending
    # Landing: Landing maneuver
    #################################
    
    Takeoff = True
    GoToBase = False
    TrackUp = False
    TrackDown= False
    Landing = False
    
    # TODO: Parameter
    cRateU = 0.90 # TODO: implies capture in 12 iterations = 0.6 seconds
    cRateD = 0.98
    
    # os.system("rosrun mavros mavsys mode -c  \"OFFBOARD\" ")
    # os.system("rosrun mavros mavcmd takeoffcur 0 0 2")
        
    while not rospy.is_shutdown():

        #####
        # Take off to one meter and then to altStep
        #####
            
        if Takeoff:
        
            print "Takeoff..."
             
            rospy.set_param('/kBodVel/feedForward', False) # turn off EKF feedforward
            rospy.set_param('/kBodVel/vMax',vMax/10.0) # reduce max lateral velocity TODO: parameter
                                
            home.x = takeoff.x
            home.y = takeoff.y   
            
            for phase in range(0,2):
                if phase == 0:
                    print "Phase 1..."
                    home.z = zGround + 2.0 # TODO: parameter
                else:
                    print "Phase 2..."
                    home.z = zGround + zHover
                
                sm.altK.zSp = home.z
                
                print "z/zSp: ", sm.altK.z, sm.altK.zSp
                
                while not abs(sm.altK.zSp - sm.altK.z) < 0.2 and not rospy.is_shutdown():
                
                    if phase == 0:
                        sm.setp.velocity.x, sm.setp.velocity.y, sm.setp.yaw_rate = 0.0, 0.0, 0.0 # no lateral tracking
                    else: # phase == 1
                        (sm.bodK.xSp,sm.bodK.ySp) = sm.wayHome(sm.bodK,home) # track takeoff x,y location
                        (sm.setp.velocity.x,sm.setp.velocity.y,sm.setp.yaw_rate) = sm.bodK.controller()
                    sm.setp.velocity.z = sm.altK.controller()
                                        
                    # Issue velocity commands
                    sm.rate.sleep()
                    sm.setp.header.stamp = rospy.Time.now()                    
                    sm.command.publish(sm.setp)
                                             
            # Cleanup
            rospy.set_param('/kBodVel/feedForward',feedForward)
            rospy.set_param('/kBodVel/vMax',vMax) # restore max lateral velocity
            
            # Prep for next mode    
            Takeoff = False
            GoToBase = True
            
        #####
        # Go to base while scanning
        #####
            
        if GoToBase:
        
            print "Go to base while scanning..."
            
            rospy.set_param('/kBodVel/feedForward', False)
            rospy.set_param('/kBodVel/vMax',vMax/2.0) # reduce max lateral velocity TODO: parameter
            
            home.x = base.x
            home.y = base.y
            home.z = zGround + zHover
            
            confidence = 0.0
            
            while confidence < 0.7 and not rospy.is_shutdown(): # TODO: parameter
            
                error = sqrt((sm.bodK.x - home.x)**2 + (sm.bodK.y - home.y)**2)

                print "GoToBase:d2h/conf: ", error, confidence
            
                if target.z > 0:
                    seeIt = True
                else:
                    seeIt = False
                
                sm.altK.zSp = home.z
                sm.setp.velocity.z = sm.altK.controller()
                
                if seeIt: # increase confidence and hold position
                    confidence = cRateU*confidence + (1-cRateU)*1.0 # TODO: Parameter
                    sm.setp.velocity.x = 0.0
                    sm.setp.velocity.y = 0.0
                    sm.setp.velocity.z = 0.0
                    sm.setp.yaw_rate = 0.0
                else: # decrease confidence and go home
                    confidence = cRateD*confidence
                    (sm.bodK.xSp,sm.bodK.ySp) = sm.wayHome(sm.bodK,home)
                    (sm.setp.velocity.x,sm.setp.velocity.y,sm.setp.yaw_rate) = sm.bodK.controller()

                sm.rate.sleep()
                sm.setp.header.stamp = rospy.Time.now()                    
                sm.command.publish(sm.setp)

            # Cleanup
            rospy.set_param('/kBodVel/feedForward',feedForward) # restore original feedforward
            rospy.set_param('/kBodVel/vMax',vMax) # restore max lateral velocity
            
            # Prep for next mode                 
            GoToBase = False
            TrackUp = True

        #####
        # Track while holding altitude
        #####
         
        if TrackUp:
        
            print "Tracking..."
        
            # Re-initialize EKF
            sm.bodK.ekf.xhat[0] = sm.bodK.x
            sm.bodK.ekf.xhat[1] = sm.bodK.y
            sm.bodK.ekf.xhat[2] = sm.bodK.yaw # current heading
            sm.bodK.ekf.xhat[3] = 0.0 # TODO: sqrt(sm.bodK.vx**2 + sm.bodK.vy**2)
            sm.bodK.ekf.xhat[4] = 0.0
            sm.bodK.ekf.P = np.matrix(np.identity(5))*1.0

            # Start time count
            tStart = rospy.Time.now()
            dT = 0.0
            
            while confidence > 0.5 and dT < 15.0 and not rospy.is_shutdown(): # TODO: parameter
            
                vxHold = sm.setp.velocity.x
                vyHold = sm.setp.velocity.y
                yrHold = sm.setp.yaw_rate
            
                if target.z > 0:
                    seeIt = True
                else:
                    seeIt = False
                    
                # Update EKF
                sm.bodK.ekfUpdate(seeIt)
                ekfState.x = sm.bodK.ekf.xhat[2]
                ekfState.y = sm.bodK.ekf.xhat[3]
                ekfState.z = sm.bodK.ekf.xhat[4]
                sm.bodK.ekfState.publish(ekfState)
                
                if seeIt: # Track target
                    confidence = cRateU*confidence + (1-cRateU)*1.0
                    altCorrect = (sm.altK.z - zGround + camOffset)/rospy.get_param('/pix2m/altCal')
                    sm.bodK.xSp = target.x*altCorrect
                    sm.bodK.ySp = target.y*altCorrect
                    (sm.setp.velocity.x,sm.setp.velocity.y,sm.setp.yaw_rate) = sm.bodK.controller()
                else: # Track EKF or momentum
                    confidence = cRateD*confidence
                    if rospy.get_param('/kBodVel/momentum'):
                        sm.setp.velocity.x = vxHold
                        sm.setp.velocity.y = vyHold
                        sm.setp.yaw_rate = yrHold
                    else:
                        home.x = sm.bodK.ekf.xhat[0]
                        home.y = sm.bodK.ekf.xhat[1]
                        (sm.bodK.xSp,sm.bodK.ySp) = sm.wayHome(sm.bodK,home)
                        (sm.setp.velocity.x,sm.setp.velocity.y,sm.setp.yaw_rate) = sm.bodK.controller()
                                
                sm.altK.zSp = zGround + zHover
                sm.setp.velocity.z = sm.altK.controller()
                
                sm.rate.sleep()
                sm.setp.header.stamp = rospy.Time.now()
                sm.command.publish(sm.setp)

                dTee = rospy.Time.now() - tStart
                dT = dTee.to_sec()
                print " "
                print "Tracking: conf", confidence
                print "dX/dY: ", sm.bodK.x - np.asscalar(sm.bodK.ekf.xhat[0]), sm.bodK.y - np.asscalar(sm.bodK.ekf.xhat[1])
                print "dT/seeIt/vHat: ", dT, seeIt, np.asscalar(sm.bodK.ekf.xhat[3])


            TrackUp = False
            if confidence < 0.51:
                GoToBase = True
            else:
                TrackDown = True

        #####
        # Track while descending
        #####
        
        if TrackDown:
        
            print "Descending..."
            
            rospy.set_param('/kAltVel/vMaxU',vMaxU/4.0)
            rospy.set_param('/kAltVel/vMaxD',vMaxD/1.0)
        
            tStart = rospy.Time.now()
            dT = 0.0
            
            smartLanding = rospy.get_param('/kAltVel/smartLanding')
            
            # theAlt = distance about ground level measurement
            
            if Testing:
                sm.altK.distanceSensor = sm.altK.z
                
            if smartLanding:
                theAlt = sm.altK.distanceSensor - zGroundDistanceSensor
            else:
                theAlt = sm.altK.z -zGround

            zSp = theAlt/2.0    # incremental target waypoint
            zFix = -1.0
            PlatformFix = False
            
            
            while confidence > 0.5 and theAlt> 0.3 and not rospy.is_shutdown(): # TODO: parameter
            
                vxHold = sm.setp.velocity.x
                vyHold = sm.setp.velocity.y
                yrHold = sm.setp.yaw_rate
                
                if Testing:
                    sm.altK.distanceSensor = sm.altK.z
                                
                if smartLanding:
                    theAlt = sm.altK.distanceSensor - zGroundDistanceSensor
                else:
                    theAlt = sm.altK.z - zGround
                    
                if theAlt < zSp + .05: # TODO: parameter
                    zSp = zSp/2.0
            
                if target.z > 0:
                    seeIt = True
                else:
                    seeIt = False
                    
                # Update EKF
                sm.bodK.ekfUpdate(seeIt)
                ekfState.x = sm.bodK.ekf.xhat[2]
                ekfState.y = sm.bodK.ekf.xhat[3]
                ekfState.z = sm.bodK.ekf.xhat[4]
                sm.bodK.ekfState.publish(ekfState)
                
                if seeIt: # Track target
                    confidence = cRateU*confidence + (1-cRateU)*1.0
                    altCorrect = (theAlt + camOffset)/rospy.get_param('/pix2m/altCal')
                    sm.bodK.xSp = target.x*altCorrect
                    sm.bodK.ySp = target.y*altCorrect
                    (sm.setp.velocity.x,sm.setp.velocity.y,sm.setp.yaw_rate) = sm.bodK.controller()
                else: # Track EKF or momentum
                    confidence = cRateD*confidence
                    if rospy.get_param('/kBodVel/momentum'):
                        sm.setp.velocity.x = vxHold
                        sm.setp.velocity.y = vyHold
                        sm.setp.yaw_rate = yrHold
                    else:
                        home.x = sm.bodK.ekf.xhat[0]
                        home.y = sm.bodK.ekf.xhat[1]
                        (sm.bodK.xSp,sm.bodK.ySp) = sm.wayHome(sm.bodK,home)
                        (sm.setp.velocity.x,sm.setp.velocity.y,sm.setp.yaw_rate) = sm.bodK.controller()
                
                Descend = False
                dXY = -1.0
                dV = -1.0

                teraMean= np.mean(sm.altK.teraRanges)
                teraAgree = False
                if max(sm.altK.teraRanges) - min(sm.altK.teraRanges) < rospy.get_param('/kAltVel/teraAgree'):
                    teraAgree = True
                
                if seeIt: # TODO: landing logic. descend blind if high confidence also?

                    dXY = sqrt(sm.bodK.xSp**2 + sm.bodK.ySp**2)
                    dV = abs(   sqrt(sm.bodK.vx**2 + sm.bodK.vy**2) - abs(np.asscalar(sm.bodK.ekf.xhat[3]))   )

                    Envelope = False
                    HighAltitude = False
                    AllAgree = False
                    
                    if dXY < 0.1*(1.0 + theAlt) and dV < 0.2: # TODO: parameters
                        Envelope = True
                    if theAlt > 2.5:
                        HighAltitude = True
                    if teraAgree: # Test if teraRanges agree with distance sensor
                        var = abs((teraMean - zGroundTera) - (sm.altK.distanceSensor - zGroundDistanceSensor))
                        if var < rospy.get_param('/kAltVel/teraAgree')/2: #TODO: parameter
                           AllAgree = True
                        elif Testing:
                            AllAgree = True
                        
                    if HighAltitude: # descend if seeIt and high altitude and platform velocity match:
                        sm.setp.velocity.z = -rospy.get_param('/kAltVel/vMaxD')
                        Descend = True
                    elif Envelope and AllAgree: # descend if seeIt and platform match and teraRangers agree with distanceSensor
                        if smartLanding: 
                            zFix = theAlt
                            vzTemp = rospy.get_param('/kAltVel/gP')*(zSp - theAlt)
                            sm.setp.velocity.z = \
                                autopilotClass.sat(vzTemp,-rospy.get_param('/kAltVel/vMaxD'),rospy.get_param('/kAltVel/vMaxU'))
                            PlatformFix = True
                            Descend = True
                        else:
                            zFix = theAlt
                            sm.altK.zSp = zSp + zGround
                            sm.setp.velocity.z = sm.altK.controller()
                            PlatformFix = True
                            Descend = True
                    elif AllAgree and not Envelope:
                        if not PlatformFix:
                            sm.setp.velocity.z = 0.0
                        else:
                            vzTemp = rospy.get_param('/kAltVel/gP')*(zFix + 2.0 - theAlt) # TODO: Platform height
                            sm.setp.velocity.z = \
                                autopilotClass.sat(vzTemp,-rospy.get_param('/kAltVel/vMaxD'),rospy.get_param('/kAltVel/vMaxU'))
                            # sm.setp.velocity.z = 0.0
                    else: # Envelope and not AllAgree:
                        sm.setp.velocity.z = 0.0
                               
                else: # seeIt is false. increase altitude towards zHover
                    sm.altK.zSp = zGround + zHover 
                    sm.setp.velocity.z = sm.altK.controller()
                           
                # Issue velocity commands
                sm.rate.sleep()
                sm.setp.header.stamp = rospy.Time.now()
                sm.command.publish(sm.setp)
                
                print " "
                print "Descending: conf/PlatformFix:", confidence, PlatformFix
                print "teras/teraAgree:", sm.altK.teraRanges, teraAgree
                print "seeIt/Env/High/AllAgree: ", seeIt, Envelope, HighAltitude, AllAgree
                print "dXY/dV/vHat: ", dXY, dV, np.asscalar(sm.bodK.ekf.xhat[3])
                print "Descend/z/zSp/zFix: ", Descend, theAlt, zSp, zFix

            TrackDown = False
            
            # Cleanup
            rospy.set_param('/kAltVel/vMaxU',vMaxU)
            rospy.set_param('/kAltVel/vMaxD',vMaxD)
            
            if confidence < 0.51:
                GoToBase = True
            else:
                Landing = True
                
        if Landing:
            
            print "Landing..."
            rospy.set_param('/kBodVel/feedForward', False)
            
            dzError = 0.0
            h = 1.0/rospy.get_param('/autopilot/fbRate')
            
            vxHold = sm.setp.velocity.x
            vyHold = sm.setp.velocity.y
            yrHold = sm.setp.yaw_rate
            
            while dzError < 1.0 and not rospy.is_shutdown(): # TODO: parameter 
            
                # update blind EKF
                sm.bodK.ekfUpdate(False)
                
                if rospy.get_param('/kBodVel/momentum'):
                    sm.setp.velocity.x = vxHold
                    sm.setp.velocity.y = vyHold
                    sm.setp.yaw_rate = yrHold
                else:
                    home.x = sm.bodK.ekf.xhat[0]
                    home.y = sm.bodK.ekf.xhat[1]
                    (sm.bodK.xSp,sm.bodK.ySp) = sm.wayHome(sm.bodK,home)
                    (sm.setp.velocity.x,sm.setp.velocity.y,sm.setp.yaw_rate) = sm.bodK.controller()          
                
                # decend constant velocity
                sm.setp.velocity.z = -0.5 # TODO: parameter
                           
                # Issue velocity commands
                sm.setp.header.stamp = rospy.Time.now()
                sm.rate.sleep()
                sm.command.publish(sm.setp)
                
                dzError = dzError + h*(sm.altK.vz - sm.setp.velocity.z) # commanded velocity - actual velocity
                print "Landing:dzError", dzError
                        
            # sm.modes.setDisarm()
            break   
        
if __name__ == '__main__':
    try:
        ch1sm()
    except rospy.ROSInterruptException:
        pass





 
