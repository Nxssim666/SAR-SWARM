from setuptools import find_packages, setup

package_name = 'sar_gcs_bridge'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Ahmed-Nassim Laatiki',
    maintainer_email='nxssim666@gmail.com',
    description='Bridge between the swarm_sar protocol (ROS 2) and the fleet service (NATS).',
    license='MIT',
    extras_require={'test': ['pytest']},
    entry_points={
        'console_scripts': [
            'bridge_node = sar_gcs_bridge.node:main',
        ],
    },
)
