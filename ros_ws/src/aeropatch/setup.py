from setuptools import find_packages, setup

package_name = "aeropatch"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["tests"]),
    data_files=[
        ("share/ament_index/resource_index/packages",
            ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch",
            ["launch/sim_launch.py", "launch/gazebo_launch.py"]),
        ("share/" + package_name + "/config",
            ["config/params.yaml", "config/params_nvidia.yaml"]),
        ("share/" + package_name + "/worlds", ["worlds/aero_world.sdf"]),
        ("share/" + package_name + "/rviz", ["rviz/aero_demo.rviz"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="AeroPatch Team",
    maintainer_email="team@aeropatch.dev",
    description="AeroPatch: edge anomaly detection with cloud (Nemotron + Tavily) patching.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "sim_node = aeropatch.sim_node:main",
            "monitor_node = aeropatch.monitor_node:main",
            "bridge_node = aeropatch.bridge_node:main",
            "controller_node = aeropatch.controller_node:main",
            "disturbance_node = aeropatch.disturbance_node:main",
            "gz_truth_node = aeropatch.gz_truth_node:main",
            "gz_disturbance_node = aeropatch.gz_disturbance_node:main",
            "gz_viz_node = aeropatch.gz_viz_node:main",
            "gz_marker_node = aeropatch.gz_marker_node:main",
            "ekf_node = aeropatch.ekf_node:main",
        ],
    },
)
