from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
	name="frappe_activity_tracker",
	version="0.0.1",
	description="Tracks user activity inside Frappe Desk and provides productivity analytics",
	author="rbnkoirala",
	author_email="",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires,
)
