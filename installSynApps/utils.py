from collections import namedtuple
from pathlib import Path
import installSynApps.logger as logger
import os
import subprocess
from subprocess import Popen, PIPE
from . import CONFIG_DIR


DEFAULT_MACROS = {
    "TIRPC": "YES",
    "STATIC_BUILD": "YES",
    "BUILD_IOCS": "YES",
    "WITH_BOOST": "NO",
    "BOOST_EXTERNAL": "YES",
    "WITH_PVA": "YES",
    "WITH_QSRV": "YES",
    "WITH_BLOSC": "YES",
    "BLOSC_EXTERNAL": "NO",
    "WITH_BITSHUFFLE": "YES",
    "BITSHUFFLE_EXTERNAL": "NO",
    "WITH_GRAPHICSMAGICK": "YES",
    "GRAPHICSMAGICK_EXTERNAL": "NO",
    "GRAPHICSMAGICK_PREFIX_SYMBOLS": "YES",
    "WITH_HDF5": "YES",
    "HDF5_EXTERNAL": "NO",
    "WITH_JSON": "YES",
    "WITH_JPEG": "YES",
    "JPEG_EXTERNAL": "NO",
    "WITH_NETCDF": "YES",
    "NETCDF_EXTERNAL": "NO",
    "WITH_NEXUS": "YES",
    "NEXUS_EXTERNAL": "NO",
    "WITH_OPENCV": "NO",
    "OPENCV_EXTERNAL": "YES",
    "WITH_OPENCV_VIDEO": "YES",
    "WITH_SZIP": "YES",
    "SZIP_EXTERNAL": "NO",
    "WITH_TIFF": "YES",
    "TIFF_EXTERNAL": "NO",
    "XML2_EXTERNAL": "NO",
    "WITH_ZLIB": "YES",
    "ZLIB_EXTERNAL": "NO",
    "ARAVIS_LIB": "/opt/aravis/lib64",
    "ARAVIS_INCLUDE": "/opt/aravis/include/aravis-0.8",
    "GLIB_INCLUDE": "/usr/include/glib-2.0 /usr/lib64/glib-2.0/include",
    "glib-2.0_DIR": "/usr/lib64"
}

DEFAULT_MODULES = {
"EPICS_BASE": {
    "URL": "https://github.com/epics-base/epics-base",
    "VERSION": "R7.0.5",
    "RECURSIVE": True
},
"IPAC": {
    "URL": "https://github.com/epics-modules/ipac",
    "VERSION": "2.16"
},
"ASYN": {
    "URL": "https://github.com/epics-modules/asyn",
    "VERSION": "R4-41"
},
"AUTOSAVE": {
    "URL": "https://github.com/epics-modules/autosave",
    "VERSION": "R5-10-2"
},
"BUSY": {
    "URL": "https://github.com/epics-modules/busy",
    "VERSION": "R1-7-3"
},
"CALC": {
    "URL": "https://github.com/epics-modules/calc",
    "VERSION": "R3-7-3"
},
"DEVIOCSTATS": {
    "URL": "https://github.com/epics-modules/iocStats",
    "VERSION": "3.2.0"
},
"SSCAN": {
    "URL": "https://github.com/epics-modules/sscan",
    "VERSION": "R2-11-3"
},
"MOTOR": {
    "URL": "https://github.com/epics-modules/motor",
    "VERSION": "R7-2-2",
    "RECURSIVE": True
},
"SNCSEQ": {
    "URL": "https://github.com/mdavidsaver/sequencer-mirror",
    "VERSION": "R2-2-9"
},
"OPTICS": {
    "URL": "https://github.com/epics-modules/optics",
    "VERSION": "R2-13-5"
},
"STREAM": {
    "URL": "https://github.com/paulscherrerinstitute/StreamDevice",
    "VERSION": "2.8.10"
},
"RECCASTER": {
    "URL": "https://github.com/ChannelFinder/recsync",
    "VERSION": "1.6"
},
"STD": {
    "URL": "https://github.com/epics-modules/std",
    "VERSION": "R3-6-2"
},
"ADSUPPORT": {
    "URL": "https://github.com/areaDetector/ADSupport",
    "VERSION": "R1-10"
},
"ADCORE": {
    "URL": "https://github.com/areaDetector/ADCore",
    "VERSION": "R3-12-1"
}
}



def get_current_module_hash(module_abs_path: Path):

    cmd = ["git", "-C", module_abs_path, "rev-parse", "HEAD"]
    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    current_hash = p.communicate()[0].decode("utf-8")[:8]
    return current_hash


def get_commit_hash_given_version(module_name: str, repository: str, version: str):
    cmd = ["git", "ls-remote", repository]
    logger.print_command(cmd)
    p = Popen(cmd, stdout=PIPE, stderr=PIPE)
    out, _  = p.communicate()
    ret = out.decode("utf-8")

    head_commit_hash = ret.splitlines[0].split("\t")[0][:8]

    frozen_version = None
    for branch_info in ret.splitlines():
        if branch_info.endswith(version) and "refs/tags" not in branch_info:
            frozen_version = branch_info.split("\t")[0][:8]
            logger.debug(f"Module {module_name} frozen to {frozen_version} from {version}.")
        elif branch_info.endswith(version) and "refs/tags" in branch_info:
            logger.debug(f"Module {module_name} already frozen to tag {version}.")

    if frozen_version is None:
        logger.debug(f"Failed to detect suitable hash to freeze {module_name} to {version}...")
        frozen_version = head_commit_hash
        logger.debug(f"Defaulting to head commit hash: {frozen_version}")

    return frozen_version


def check_dependency_in_path(dependency: str):
    """Function meant to check if required packages are located in the system path.

    Returns
    -------
    bool
        True if success, False if error
    str
        Empty string if success, otherwise name of mssing dependency
    """

    with open(os.devnull, 'w') as fn:
        try:
            subprocess.call([dependency, "--version"], stdout=fn, stderr=fn)
        except FileNotFoundError:
            raise RuntimeError(f"Dependency {dependency} not found in system path!")


def check_for_required_dependencies():
    for dep in ["make", "perl", "git", "tar"]:
        check_dependency_in_path(dep)

def get_active_environment():
    """Function that gets the active environment from the epicsenv settings file.

    Returns
    -------
    str
        The name of the active environment
    """

    epics_env_settings = os.path.join(CONFIG_DIR, "epicsenv.ini")
    if not os.path.exists(epics_env_settings):
        return None
    else:
        with open(epics_env_settings, 'r') as fp:
            for line in fp:
                if line.startswith("ACTIVE_ENV="):
                    return line.split("=")[1].strip()
    return None

def get_module_configure_dirs(module_abs_path: Path) -> list[tuple[Path, list[str]]]:
    configure_dirs = []
    for dirpath, _, filenames in os.walk(module_abs_path):
        if os.path.basename(dirpath) == "configure":
            configure_dirs.append((dirpath, filenames))
    return configure_dirs