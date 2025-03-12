"""A python module that helps in downloading, building, and packaging EPICS, synApps and areaDetector.

installSynApps has two primary clients, installCLI, and installGUI, which allow for different ways to 
clone build and package specified modules.
"""

import sys
import os
from sys import platform
import subprocess
from . import logger

# Only support 64 bit windows
if platform == 'win32':
    OS_class = 'windows-x64'
    CONFIG_DIR = os.path.join(os.getenv('APPDATA'), 'epicsenv')
elif platform == 'darwin':
    OS_class = 'MacOS'
    CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.config', 'epicsenv')
else:
    try:
        # External package used to identify linux distribution version. Note that this adds external
        # dependancy, but it is required because the platform.linuxdistro() function is being deprecated
        import distro
        v = distro.linux_distribution(full_distribution_name=False)
        OS_class = '{}_{}'.format(v[0], v[1])
    except:
        OS_class='linux'
    CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.config', 'epicsenv')

# Module version, author, copyright
__version__     = "R3-0"
__author__      = "Jakub Wlodek"
__copyright__   = "Copyright (c) Brookhaven National Laboratory 2018-2025"
__environment__ = f"Python Version: {sys.version.split()[0]}, OS Class: {OS_class}"


def find_isa_version():
    """Function that attempts to get the version of installSynApps used.

    Returns
    -------
    isa_version : str
        The version string for installSynApps. Either hardcoded version, or git tag description
    commit_hash : str
        None if git status not available, otherwise hash of current installSynApps commit.
    """

    isa_version = __version__
    commit_hash = None

    try:
        logger.debug('git describe --tags')
        FNULL = open(os.devnull, 'w')
        out = subprocess.check_output(['git', 'describe', '--tags'], stderr=FNULL)
        isa_version = out.decode('utf-8').strip()
        logger.debug('git rev-parse HEAD')
        out = subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=FNULL)
        commit_hash = out.decode('utf-8')
        FNULL.close()
    except PermissionError:
        logger.debug('Could not find git information for installSynApps versions, defaulting to internal version.')
    except subprocess.CalledProcessError:
        logger.debug('Running from non-git version of installSynApps, default to internal version number.')

    logger.debug('Found installSynApps version: {}'.format(isa_version))
    return isa_version, commit_hash



def get_welcome_text():
    """Function that returns a welcome message with some installSynApps information

    Returns
    -------
    str
        the welcome message
    """

    text = "+----------------------------------------------------------------+\n"
    text = text + "+ epicsenv, Version: {:<44}+\n".format(__version__)
    text = text + "+ {:<63}+\n".format(__environment__)
    text = text + "+ {:<63}+\n".format(__copyright__)
    text = text + "+ This software comes with NO warranty!                          +\n"
    text = text + "+----------------------------------------------------------------+\n"
    return text