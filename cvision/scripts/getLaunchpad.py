#!/usr/bin/env python

import rospy
import numpy as np
import cv2
import imutils

from math import sqrt
from geometry_msgs.msg import Point32
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image

# Check version of OpenCV

if cv2.__version__.startswith('2'):
    OLDCV = True
else:
    OLDCV = False
    
if OLDCV:
    import cv2.cv as cv

import cvisionLib
import cvisionParams
cvisionParams.setParams()

###################################

def getLaunchpad():

    # Initialize node

    rospy.init_node('launchpadTracker', anonymous=True)
    
    # Create publishers
    targetPixels = rospy.Publisher('/getLaunchpad/launchpad/xyPixels', Point32, queue_size=10)
    msgPixels = Point32()
    targetMeters = rospy.Publisher('/getLaunchpad/launchpad/xyMeters', Point32, queue_size=10)
    msgMeters = Point32()
    img_pub	 = 	   rospy.Publisher('/getLaunchpad/launchpad/processedImage', Image, queue_size=10)
    bridge = CvBridge()
    
    # create subscribers to launchpad detectors
    getWhite = cvisionLib.xyzVar()
    rospy.Subscriber('/getLaunchpad/white/xyPixels', Point32, getWhite.cbXYZ)
    getCorners = cvisionLib.xyzVar()
    rospy.Subscriber('/getLaunchpad/corners/xyPixels', Point32, getCorners.cbXYZ)
    getCircle = cvisionLib.xyzVar()
    rospy.Subscriber('/getLaunchpad/circle/xyPixels', Point32, getCircle.cbXYZ)
    
    # Create setpoint generator
    spGen = cvisionLib.pix2m() # setpoint generator

    # establish publish rate
    rate = rospy.Rate(rospy.get_param('/cvision/loopRate'))

    # initializations
    
    kc = 0              # iteration counter for downsample image streaming
    Detect = False      # for detection logic
    DetectHold = False
    TOL = 2.0

    # start video stream: Replaces
    #   cap = cv2.VideoCapture(0) or cap = cv2.VideoCapture('file.mp4')
    #   _, frame = cap.read()
    quadCam = cvisionLib.getFrame()
    
    while not rospy.is_shutdown():

        # detection acceptance logic
        if getWhite.z > 0:
            detectWhite = True
        else:
            detectWhite = False
        
        if getCorners.z > 0:
            detectCorners = True
        else:
            detectCorners = False
            
        if getCircle.z > 0:
            detectCircle = True
        else:
            detectCircle = False
        
        Detect = False
        Skip = False
        CX = -1
        CY = -1

        if detectWhite and detectCorners and not Skip: # Superwhite centroid + Corners
            error = (getWhite.x - getCorners.x)**2 + (getWhite.y - getCorners.y)**2
            if sqrt(error) < TOL*getWhite.z:
                Detect = True
                CX = getCorners.x
                CY = getCorners.y
                Skip = True

        if detectCircle and detectCorners and not Skip: # Circle + Corners
            error = (getCircle.x - getCorners.x)**2 + (getCircle.y - getCorners.y)**2
            if sqrt(error) < TOL*getCircle.z:
                Detect = True
                CX = getCorners.x
                CY = getCorners.y
                Skip = True 
                               
        if detectCircle and detectWhite and not Skip: # Circle + Superwhite centroid
            error = (getCircle.x - getWhite.x)**2 + (getCircle.y - getWhite.y)**2
            if sqrt(error) < TOL*getCircle.z:
                Detect = True
                CX = getCircle.x
                CY = getCircle.y
                Skip = True  
        
        if Detect:
            msgPixels.x = CX
            msgPixels.y = CY
            msgPixels.z = 1.0
        else:
            msgPixels.x = -1.0
            msgPixels.y = -1.0
            msgPixels.z = -1.0
            
        DetectHold = Detect # hold for next iteration
        
        # publish (unrotated) pixels and (rotated) meters
        
        rate.sleep()
        
        targetPixels.publish(msgPixels)

            
        if rospy.get_param('/cvision/camRotate') and msgPixels.z > 0:        # rotate camera if needed
            msgPixels.x, msgPixels.y = cvisionLib.camRotate(msgPixels.x, msgPixels.y)

        if rospy.get_param('/cvision/feCamera'):                             # convert pixels to to meters
            (msgMeters.x, msgMeters.y, msgMeters.z) = spGen.targetFishEye(msgPixels)
        else:
            (msgMeters.x, msgMeters.y, msgMeters.z) = spGen.target(msgPixels)

        targetMeters.publish(msgMeters)
        
        
        frame = quadCam.BGR
        if getWhite.z > 0:
            cv2.circle(frame, (int(getWhite.x), int(getWhite.y)), int(getWhite.z),(255, 255, 255), 5)
        if getCircle.z > 0:
            cv2.circle(frame, (int(getCircle.x), int(getCircle.y)), int(getCircle.z),(0, 255, 0), 5)
        if getCorners.z > 0:
            cv2.circle(frame, (int(getCorners.x), int(getCorners.y)), 10,(0, 255, 255), -1)
        if Detect:
            cv2.circle(frame, (int(CX), int(CY)), 10,(0, 0, 255), -1)

        # show processed images to screen
        if rospy.get_param('/getLaunchpad/imgShow'):
            cv2.imshow('launchpad',frame)
            #cv2.imshow('pxMask',pxMask)
            key = cv2.waitKey(1) & 0xFF

        # published downsized/grayscale processed image
        STREAM_RATE = rospy.get_param('/getLaunchpad/imgStreamRate')
        if rospy.get_param('/getLaunchpad/imgStream'): # stream processed image
            if (kc*STREAM_RATE)%rospy.get_param('/cvision/loopRate') < STREAM_RATE:
                gray_frame=cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray_frame=imutils.resize(gray_frame, width=rospy.get_param('/cvision/LX')/2)
                img_pub.publish(bridge.cv2_to_imgmsg(gray_frame, encoding="passthrough"))
                
        kc = kc + 1

if __name__ == '__main__':
    try:
        getLaunchpad()
    except rospy.ROSInterruptException:
        cap.release()
        cv2.destroyAllWindows()
        pass
