from glob import glob

from setuptools import find_packages, setup

package_name = 'swarm_sar'

setup(
    name=package_name,
    version='2.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Ahmed-Nassim Laatiki',
    maintainer_email='nxssim666@gmail.com',
    description='Search-and-rescue drone swarm for PX4 multicopters with depth cameras.',
    license='MIT',
    extras_require={'test': ['pytest'], 'render': ['matplotlib']},
    entry_points={
        'console_scripts': [
            'drone_node = swarm_sar.ros.drone_node:main',
            'monitor_node = swarm_sar.ros.monitor_node:main',
            'swarm_sar_mission = swarm_sar.ros.mission_cli:main',
            'swarm_sar_sim = swarm_sar.standalone:cli',
        ],
    },
)
