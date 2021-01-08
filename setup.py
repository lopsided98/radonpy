from setuptools import setup, find_packages

setup(
    name='radonpy',
    version='0.1.0',
    author='Ben Wolsieffer',
    author_email='benwolsieffer@gmail.com',
    description='Tools to communicate with the RadonEye RD200 radon detector',
    license='Apache License 2.0',
    keywords=['radon' 'radoneye'],
    url='http://packages.python.org/radonpy',
    long_description=open('README.md').read(),
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Topic :: Home Automation',
        'License :: OSI Approved :: Apache Software License',
    ],
    install_requires=[
        'bleak',
        'aioinflux'
    ],
    packages=find_packages(),
    entry_points={
        'console_scripts': ['radonpy=radonpy.main:main'],
    }
)
