"""A file containing representations of install configurations.

The core Data representations for installSynApps. 

InstallModule objects are used to represent each module defined in the configuration.
They store all module-specific information pertinent to building and cloning it.

An InstallConfiguration object is parsed from a configuration, and is then used throughout the build process.
"""

import os
from pathlib import Path
import re
from subprocess import Popen, PIPE
from . import logger
import json
from .utils import get_commit_hash_given_version

# Because EPICS versioning is not as standardized as it should be, certain modules cannot be properly auto updated.
# Ex. Calc version R3-7-3 is most recent, but R5-* exists?
UPDATE_TAGS_BLACKLIST = ["SSCAN", "CALC", "STREAM"]

class InstallModule:
    """Class that represents individual install module

    Attributes
    ----------
    name : str
        the name of the module
    version : str
        the desired module tag, or alternatively master
    rel_path : str
        relative path to module
    abs_path : str
        absolute path to module
    url_type : str
        either GIT_URL if using git version control, or WGET_URL if sources hosted in .tar.gz file
    url : str
        url where the git repository or wget download resies
    repository : str
        name of the git repo to clone or wget file to download
    clone : str
        YES or NO, flag to clone the module
    build : str
        YES or NO, flag to build the module
    package : str
        YES or NO, flag to package the module
    custom_build_script_path : str
        path to script used to build module instead of just make
    dependencies : list of str
        list of modules identified as dependencies for module
    """

    def __init__(self, module_name: str, module_config: dict[str, dict[str, str]]):
        """Constructor for the InstallModule class
        """

        self.name = module_name
        self.version = module_config["VERSION"]
        self.url = module_config["URL"]
        self.module_dir_name = self.url.split("/")[-1]
        self.cloned = False
        self.built = False
        self.installed = False

        self.build_cmd = None
        if "BUILD_CMD" in module_config:
            self.build_cmd = module_config["BUILD_CMD"]

        self.recursive_clone = False
        if "RECURSIVE" in module_config and module_config["RECURSIVE"]:
            self.recursive_clone = True

        if "STATE" in module_config:
            self.cloned = module_config["STATE"] & 1
            self.built = module_config["STATE"] & 2
            self.installed = module_config["STATE"] & 4
            

        # List of epics modules that this module depends on
        self.dependencies = []


    def as_dict(self) -> dict:
        as_dict = {}
        as_dict["URL"] = self.url
        as_dict["VERSION"] = self.version
        if self.build_cmd is not None:
            as_dict["BUILD_CMD"] = self.build_cmd
        if self.recursive_clone:
            as_dict["RECURSIVE"] = True
        as_dict["STATE"] = 1 * self.cloned + 2 * self.built + 4 * self.installed
        as_dict["DEPS"] = self.dependencies

        return as_dict


class InstallConfiguration:
    """
    Class that represents an Install Configuration for installSynApps
    
    It stores the top level install_location, the path to the configuration files,
    any OS specific configurations, and the actual list of modules that will be 
    installed.

    Attributes
    ----------
    install_location : str
        path to top level install location
    config_path : str
        path to configure folder of installSynApps
    modules : List of InsallModule
        list of InstallModule objects representing the modules that will be installed
    base_path : str
        abs path to install location of EPICS base
    support_path : str
        abs path to install location of EPICS support modules
    ad_path : str
        abs path to install location of EPICS area detector
    motor_path : str
        abs path to install location of EPICS motor
    module_map : dict of str -> int
        Dictionary storing relation of module names to build index
    injector_files : list of InjectorFile
        list of injector files loaded by install configuration
    build_flags : list of list of str
        list of macro-value pairs enforced at build time
    """


    def __init__(self, config_file_path: Path | None = None):
        """Constructor for the InstallConfiguration object
        """

        # Paths to configure and output locations
        self.config_file_path = config_file_path

        self.install_location = None
        self.build_location = None
        self.cloned = False
        self.modules: dict[str, InstallModule] = {}
        self.build_options: dict[str, str] = {}

        if config_file_path is not None:
            with open(config_file_path, "r") as fp:
                configuration = json.loads(fp.read())
                self.install_location = configuration["INSTALL_LOC"]
                self.build_location = configuration["BUILD_LOC"]

                modules_as_json = configuration["MODULES"]
                for module_name in modules_as_json:
                    self.modules[module_name] = InstallModule(module_name, modules_as_json[module_name])

                self.build_options = configuration["CONFIG_MACROS"]


    def save(self, save_path: Path | None = None, overwrite_existing=True):
        """Function that saves loaded install configuration

        Main saving function for writing install config. Can create a save directory, then saves 
        main install configuration, build flags, and injector files.

        Parameters
        ----------
        filepath : str
            defaults to addtlConfDirs/config$DATE. The filepath into which to save the install configuration

        Returns
        -------
        bool
            True if successful, False otherwise
        str
            None if successfull, otherwise error message
        """

        if save_path is None:
            save_path = self.config_file_path

        if overwrite_existing and os.path.exists(save_path):
            os.remove(save_path)
        elif not overwrite_existing and os.path.exists(save_path):
            raise FileExistsError(f"Configuration already written to {save_path}!")

        with open(save_path, "w") as fp:
            configuration = {}

            configuration["BUILD_LOC"] = self.build_location
            configuration["INSTALL_LOC"] = self.install_location
            configuration["CONFIG_MACROS"] = self.build_options
            configuration["MODULES"] = {}
            for module_name in self.modules:
                configuration["MODULES"][module_name] = self.modules[module_name].as_dict()

            fp.write(json.dumps(configuration, indent=4))


    def freeze(self):
        logger.write("Freezing versions of modules in configuration...")
        for module in self.modules.values():
            logger.write(f"Freezing version of {module.name}...")
            module.version = get_commit_hash_given_version(module.name, module.url, module.version)
            logger.write(f"Froze module to hash {module.version}")
        logger.write("Done.")


    def clear_clone_and_build_state(self, modified_module):
        modified_module.cloned = False
        modified_module.built = False
        modified_module.installed = False
        for module in self.modules.values():
            if modified_module in module.dependencies:
                self.clear_clone_and_build_state(module)


    def auto_update_module_tag(self, module: InstallModule):
        """Function that syncs module version tags with those hosted with git.

        Parameters
        ----------
        module_name : str
            The name of the module to sync
        install_config : InstallConfiguration
            instance of install configuration for which to update tags
        save_path : str
            None by default. If set, will save the install configuration to the given location after updating.
        """

        if module.version not in ["master", "main"] and module.name not in UPDATE_TAGS_BLACKLIST:
            cmd = ["git", "ls-remote", "--tags", module.url]
            logger.print_command(cmd)
            p = Popen(cmd, stdout=PIPE, stderr=PIPE)
            out, _ = p.communicate()
            ret = out.decode("utf-8")
            
            best_tag = None
            for tag_info in ret.splitlines():
                tag = tag_info.rsplit("/")[-1]

                if best_tag is None:
                    best_tag = tag
                else:
                    best_tag_ver_str_list = re.split(r"\D+", best_tag)
                    best_tag_ver_str_list = [num for num in best_tag_ver_str_list if num.isnumeric()]
                    best_tag_version_numbers = list(map(int, best_tag_ver_str_list))
                    
                    tag_ver_str_list = re.split(r"\D+", tag)
                    tag_ver_str_list = [num for num in tag_ver_str_list if num.isnumeric()]
                    tag_version_numbers = list(map(int, tag_ver_str_list))
                    for i in range(len(tag_version_numbers)):
                        if best_tag.startswith("R") and not tag.startswith("R"):
                            break
                        elif not best_tag.startswith("R") and tag.startswith("R"):
                            best_tag = tag
                            best_tag_version_numbers = tag_version_numbers
                            break
                        elif i == len(best_tag_version_numbers) or tag_version_numbers[i] > best_tag_version_numbers[i]:
                            best_tag = tag
                            best_tag_version_numbers = tag_version_numbers
                            break
                        elif tag_version_numbers[i] < best_tag_version_numbers[i]:
                            break

                tag_updated = False
                module_ver_str_list = re.split(r"\D+", module.version)
                module_ver_str_list = [num for num in module_ver_str_list if num.isnumeric()]
                module_version_numbers = list(map(int, module_ver_str_list))

                for i in range(len(best_tag_version_numbers)):
                    if i == len(module_version_numbers) or best_tag_version_numbers[i] > module_version_numbers[i]:
                        tag_updated = True
                        logger.write(f"Updating {module.name} from version {module.version} to version {best_tag}")
                        module.version = best_tag
                        self.clear_clone_and_build_state(module)

                        break
                    elif best_tag_version_numbers[i] < module_version_numbers[i]:
                        break
                if not tag_updated:
                    logger.debug(f"Module {module.name} already at latest version: {module.version}")


    def auto_update_modules(self, save_path=None, overwrite_existing=True):
        """Function that syncs module version tags with those found in git repositories.

        Parameters
        ----------
        install_config : InstallConfiguration
            instance of install configuration for which to update tags
        save_path : str
            None by default. If set, will save the install configuration to the given location after updating.
        overwrite_existing : bool
            Flag that tells installSynApps to overwrite or not the existing module tags. Default: True
        """

        logger.write('Syncing...')
        logger.write('Please wait while tags are synced - this may take a while...')
        for module in self.modules.values():
            self.auto_update_module_tag(module)


    def __str__(self) -> str:

        out = "--------------------------------\n"
        out = out + f"Config Location {self.config_file_path}\n"
        out = out + f"Build Location = {self.build_location}\n"
        out = out + f"Install Location = {self.install_location}\n\nModules:\n\n"
        out = out + f"+------------------------------------------------------------------+\n"
        out = out + f"|     Module Name    | Module Version | Cloned | Built | Installed |\n"
        out = out + f"+------------------------------------------------------------------+\n"
        for module in self.modules.values():
            out += f"|   {module.name:16} |   {module.version:12} | {'X' if module.cloned else ' '}      | {'X' if module.built else ' '}        | {'X' if module.installed else ' '}      |\n"
        out = out + f"+------------------------------------------------------------------+\n"
        return out