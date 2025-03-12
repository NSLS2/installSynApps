

from pathlib import Path
from installSynApps.data_model import InstallConfiguration, InstallModule
from subprocess import Popen
import subprocess
import os
import installSynApps.logger as logger
from installSynApps.utils import check_dependency_in_path
from .clone import clone_single_module
from .utils import get_module_configure_dirs

# Currently only support auto-fetching dependencies w/ dnf
BASE_DEPS_DNF = [
    "re2c",
    "readline-devel",
    "libxml2-devel",
    "pcre-devel",
    "libtirpc-devel",
    "libusbx-devel",
    "git",
    "make",
    "gcc",
    "gcc-g++",
    "libXext-devel",
    "perl-devel",
    "libraw1394",
    "boost-devel",
    "libusb-devel",
    "rpcgen",
    "net-snmp-devel",
    "motif-devel",
    "libXt-devel",
    "zeromq-devel",
    "giflib-devel",
    "libXtst-devel"
]

def acquire_dependecies():
    """Method that runs dependency install shell/batch script

    Parameters
    ----------
    dependency_script_path : str
        path to dependency shell/batch script
    """

    logger.debug("Installing dependency packages...")
    try:
        check_dependency_in_path("dnf")
    except RuntimeError:
        logger.debug("Dependency auto-installation only supported on RH derivatives.")
    else:
        cmd = []
        if os.geteuid == 0:
            pass
        else:
            try:
                check_dependency_in_path("dzdo")
                cmd.append("dzdo")
            except RuntimeError:
                cmd.append("sudo")
        cmd.extend(["dnf", "install", "-y"])

        for pkg in BASE_DEPS_DNF:
            logger.debug(f"Installing {pkg} with dnf...")
            subprocess.call(cmd + pkg)



def build_single_module(install_config: InstallConfiguration, module: InstallModule, num_threads: int = 0):
    """Function that executes build of single module

    First, checks if all dependencies built, if not, does that first.
    Then checks for custom build script. If one is found, runs that from
    module root directory.
    Otherwise, runs make followed by specified make flag in module root
    directory.

    Parameters
    ----------
    module_name : str
        The name of the module being built

    Returns
    -------
    int
        The return code of the build process, 0 if module is not buildable (ex. UTILS)
    """


    if module.built:
        logger.write(f"Module {module.name} already built.")
        return True

    if not module.cloned:
        cloned = clone_single_module(install_config.build_location, module)
        if not cloned:
            return False

    for dep in module.dependencies:
        deps_built = build_single_module(install_config, install_config.modules[dep], num_threads=num_threads)
        if not deps_built:
            return False

    module_abs_path = os.path.join(install_config.build_location, module.url.split('/')[-1].split('.')[0])

    if module.name != "EPICS_BASE":
        logger.write(f"Replacing CONFIG_SITE and RELEASE files for {module.name}")
        for configure_dir, filenames in get_module_configure_dirs(module_abs_path):
            for file in filenames:
                if file.startswith("CONFIG_SITE") or file.startswith("RELEASE"):
                    os.remove(os.path.join(configure_dir, file))
            with open(os.path.join(configure_dir, "CONFIG_SITE"), "w") as fp:
                for macro in install_config.build_options:
                    fp.write(f"{macro}={install_config.build_options[macro]}\n")
            with open(os.path.join(configure_dir, "RELEASE"), "w") as fp:
                for mod in install_config.modules.values():
                    fp.write(f"{mod.name}={os.path.join(install_config.build_location, mod.url.split('/')[-1].split('.')[0])}\n")

    logger.write(f"Building module {module.name}")
    if module.build_cmd is not None:
        cmd = module.build_cmd.split(" ")
    else:
        cmd = ["make", "-C", module_abs_path, f"-sj{'' if num_threads == 0 else num_threads}"]
    
    logger.print_command(cmd)
    proc = Popen(cmd)
    proc.wait()
    ret = proc.returncode
    if ret == 0:
        module.built = True
        return True

    return False


def build_all(install_config: InstallConfiguration, num_threads: int = 0):
    """Main function that runs full build sequentially

    Returns
    -------
    int
        0 if success, number failed modules otherwise
    list of str
        List of module names that failed to compile
    """

    failed = []
    for module in install_config.modules.values():
        built_successfully = build_single_module(install_config, module, num_threads=num_threads)
        install_config.save()
        if not built_successfully:
            failed.append(module)

    return failed
