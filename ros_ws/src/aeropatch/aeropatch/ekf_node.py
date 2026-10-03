import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu

class EKFNode(Node):
    def __init__(self):
        super().__init__('ekf_node')
        self.subscription = self.create_subscription(Odometry, '/odom', self.odom_callback, 10)
        self.publisher = self.create_publisher(Odometry, '/odometry/filtered', 10)
        self.get_logger().info('EKF Node initialized (passthrough mode).')

    def odom_callback(self, msg):
        # EKF füzyon mantığı burada geliştirilecek
        self.publisher.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = EKFNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()