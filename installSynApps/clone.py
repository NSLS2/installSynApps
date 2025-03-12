from pathlib import Path
import re
from installSynApps import logger
import os
import shutil
from installSynApps.data_model import InstallConfiguration, InstallModule
from installSynApps.utils import get_commit_hash_given_version, get_current_module_hash
from subprocess import Popen, PIPE
from .utils import get_module_configure_dirs

# Variables set in RELEASE file that are not module dependencies
NON_DEP_RELEASES = [
    "SUPPORT", 
    "UTILS", 
    "TEMPLATE_TOP", 
    "TEMPLATE_CONFIG", 
    "TEMPLATE_RELEASE", 
    "TEMPLATE_SITE", 
    "TEMPLATE_CONFIG_SITE",
]


def clone_single_module(build_loc: Path, module: InstallModule) -> bool:
    """Function responsible for cloning each module into the appropriate location

    First checks if the module uses git or a download, and whether it needs to be recursive
    then, uses the information in the module object along with subprocess commands to clone the module.

    Parameters
    ----------
    module : InstallModule
        InstallModule currently being cloned
    recursive=False
        Flag that decides if git clone should be done recursively
    """

    cloned: bool = False

    logger.debug(f"Cloning module {module.name}...")

    module_abs_path = os.path.join(build_loc, module.url.split('/')[-1].split('.')[0])
    
    if module.cloned:
        logger.write(f"Module {module.name} already cloned.")
        return True
    elif os.path.exists(module_abs_path):
        logger.debug(f"Module {module.name} already exists in build location, but with the wrong version.")
        shutil.rmtree(module_abs_path)

    cmd = ["git", "clone"]
    if module.recursive_clone:
        cmd.append("--recursive")
    cmd.extend([module.url, module_abs_path])

    logger.print_command(cmd)
    proc = Popen(cmd)
    proc.wait()
    ret = proc.returncode

    if ret != 0:
        logger.write(f"Failed to clone module {module.name}!")
        return False

    logger.write(f"Cloned module {module.name} successfully, checking out specified version...")

    cmd = ["git", "-C", module_abs_path, "checkout", "-q", module.version]
    logger.print_command(cmd)
    proc = Popen(cmd)
    proc.wait()
    ret = proc.returncode

    if ret != 0:
        logger.write(f"Checkout of version {module.version} failed for module {module.name}.")
        return False

    if module.recursive_clone:
        cmd = ["git", "-C", module_abs_path, "submodule", "update"]
        logger.print_command(cmd)
        proc = Popen(cmd)
        proc.wait()
        ret = proc.returncode

    if ret != 0:
        logger.write(f"Failed to update submodules for module {module.name}.")
        return False

    logger.write(f"Checked out version {module.version}, updating dependency information...")
    configure_dirs = get_module_configure_dirs(module_abs_path)
    for configure_dir, filenames in configure_dirs:
        for file in filenames:
            if file.startswith("RELEASE"):
                with open(os.path.join(configure_dir, "RELEASE"), "r") as fp:
                    lines = fp.readlines()
                    for line in lines:
                        line = re.sub(r'(?m)^ *#.*\n?', '', line)
                        if "=" in line:
                            dep = line.split("=")[0].strip()
                            if dep not in NON_DEP_RELEASES and dep != module.name and module.name != "EPICS_BASE":
                                module.dependencies.append(dep)
                                logger.debug(f"Detected dependency: {dep}")

    module.cloned = True
    return True


def clone_and_checkout_config(install_config: InstallConfiguration) -> list[str]:
    """Top level function that clones and checks out all modules in the current install configuration.

    Returns
    -------
    list[str]
        List of all modules that failed to be correctly cloned and checked out
    """

    failed_modules = []
    for module in install_config.modules.values():
        successfully_cloned = clone_single_module(install_config.build_location, module)
        install_config.save()
        if not successfully_cloned:
            failed_modules.append(module.name)

    return failed_modules