import re
import os
from setuptools import setup

f = open(os.path.join(os.path.dirname(__file__), 'juggernaut.py'))
doc = '\n'.join([x[4:] for x in re.search(r'"""(.*?)"""(?s)',
    f.read()).group(1).splitlines()])
f.close()


setup(
    name='juggernaut',
    author='Armin Ronacher',
    author_email='armin.ronacher@active-4.com',
    version='0.1',
    url='http://github.com/mitsuhiko/itsdangerous',
    py_modules=['juggernaut'],
    description='Client library for juggernaut.',
    long_description=doc,
    zip_safe=False,
    install_requires=['redis'],
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python'
    ]
)
