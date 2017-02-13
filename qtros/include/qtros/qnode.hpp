/**
 * @file /include/qtros/qnode.hpp
 *
 * @brief Communications central!
 *
 * @date February 2011
 **/
/*****************************************************************************
** Ifdefs
*****************************************************************************/

#ifndef qtros_QNODE_HPP_
#define qtros_QNODE_HPP_

/*****************************************************************************
** Includes
*****************************************************************************/

#include <ros/ros.h>
#include <geometry_msgs/Twist.h>
#include <mavros_msgs/Altitude.h>
#include <sensor_msgs/BatteryState.h>
#include <geometry_msgs/PoseStamped.h>
#include <geometry_msgs/TwistStamped.h>
#include <autopilots/StateMachine.h>
#include <mavros_msgs/CommandBool.h>
#include <std_msgs/String.h>
#include <string>
#include <QThread>
#include <QStringListModel>
#include <QtGui>
#include <QMessageBox>
#include <iostream>
#include <ros/network.h>
#include <sstream>
#include <string>
#include <QMetaType>
#include <QByteArray>
#define PI 3.141592653


/*****************************************************************************
** Namespaces
*****************************************************************************/
using namespace std;
namespace qtros
{

/*****************************************************************************
** Class
*****************************************************************************/

class QNode : public QThread
{
    Q_OBJECT
public:
	QNode(int argc, char** argv );
	virtual ~QNode();
	bool init();
	bool init(const std::string &master_url, const std::string &host_url);
	void run();
  void chatterCallback(const geometry_msgs::Twist::ConstPtr& msg);
  void chatterCallback2(const geometry_msgs::Twist::ConstPtr& msg);
  void AltitudeCallback1(const mavros_msgs::Altitude::ConstPtr& msg);
  void AltitudeCallback2(const mavros_msgs::Altitude::ConstPtr& msg);
  void AltitudeCallback3(const mavros_msgs::Altitude::ConstPtr& msg);
  void BatteryCallback1(const sensor_msgs::BatteryState::ConstPtr& msg);
  void BatteryCallback2(const sensor_msgs::BatteryState::ConstPtr& msg);
  void BatteryCallback3(const sensor_msgs::BatteryState::ConstPtr& msg);
  void PositionCallback1(const geometry_msgs::PoseStamped::ConstPtr& msg);
  void PositionCallback2(const geometry_msgs::PoseStamped::ConstPtr& msg);
  void PositionCallback3(const geometry_msgs::PoseStamped::ConstPtr& msg);
  void VelocityCallback1(const geometry_msgs::TwistStamped::ConstPtr& msg);
  void VelocityCallback2(const geometry_msgs::TwistStamped::ConstPtr& msg);
  void VelocityCallback3(const geometry_msgs::TwistStamped::ConstPtr& msg);
  void StateMachineCallback1(const autopilots::StateMachine::ConstPtr& msg);

	/*********************
	** Logging
	**********************/
	enum LogLevel {
	         Debug,
	         Info,
	         Warn,
	         Error,
	         Fatal
	 };

	QStringListModel* loggingModel() { return &logging_model; }
	void log( const LogLevel &level, const std::string &msg);

  void InterruptSlot1();
  void ResumeSlot1();

Q_SIGNALS:
	void loggingUpdated();
  void rosShutdown();
  void CallBackTrigger(float,float);
  void CallBackTrigger2(float,float);
  void AltitudeSignal1(float);
  void AltitudeSignal2(float);
  void AltitudeSignal3(float);
  void BatterySignal1(float,float);
  void BatterySignal2(float,float);
  void BatterySignal3(float,float);
  void PositionSignal1(float,float,float);
  void PositionSignal2(float,float,float);
  void PositionSignal3(float,float,float);
  void VelocitySignal1(float,float,float);
  void VelocitySignal2(float,float,float);
  void VelocitySignal3(float,float,float);
  void StateMachineSignal1(string,string);

private:
	int init_argc;
	char** init_argv;
	ros::Publisher chatter_publisher;
  ros::Subscriber chatter_subscriber;
  ros::Subscriber chatter_subscriber2;
  ros::Subscriber AltitudeSubscriber1;
  ros::Subscriber AltitudeSubscriber2;
  ros::Subscriber AltitudeSubscriber3;
  ros::Subscriber BatterySubscriber1;
  ros::Subscriber BatterySubscriber2;
  ros::Subscriber BatterySubscriber3;
  ros::Subscriber PositionSubscriber1;
  ros::Subscriber PositionSubscriber2;
  ros::Subscriber PositionSubscriber3;
  ros::Subscriber VelocitySubscriber1;
  ros::Subscriber VelocitySubscriber2;
  ros::Subscriber VelocitySubscriber3;
  ros::Subscriber StateMachineSubscriber1;
  QStringListModel logging_model;

};
}
#endif /* qtros_QNODE_HPP_ */