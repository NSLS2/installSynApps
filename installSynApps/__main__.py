#!/usr/bin/env python3

"""Python script for running the installSynApps module through the CLI

usage: installCLI.py [-h] [-b BUILDPATH] [-i INSTALLPATH] [-c CUSTOMCONFIGURE]
                     [-n] [-v] [-y] [-r] [-f] [-a] [-s] [-t THREADS] [-l] [-d]
                     [-p]

Utility for CLI EPICS and synApps auto-compilation

optional arguments:
  -h, --help            show this help message and exit

configuration options:
  -b BUILDPATH, --buildpath BUILDPATH
                        Define a build location that will override the one
                        found in the INSTALL_CONFIG file.
  -i INSTALLPATH, --installpath INSTALLPATH
                        Define an install location for where to output bundle
                        tarball or folder structure. Defaults to DEPLOYMENTS
  -c CUSTOMCONFIGURE, --customconfigure CUSTOMCONFIGURE
                        Use an external configuration directory. Note that it
                        must have the same structure as the default one.
  -n, --newconfig       Add this flag to use epics-install to create a new
                        install configuration.
  -v, --updateversions  Add this flag to update module versions based on
                        github tags. Must be used with -c flag.

build options:
  -y, --forceyes        Add this flag to automatically go through all of the
                        installation steps without prompts.
  -r, --requirements    Add this flag to install dependencies via a dependency
                        script.
  -f, --flatbinaries    Add this flag if you wish for output binary bundles to
                        have a flat (debian-packaging-like) format.
  -a, --archive         Add this flag to output the bundle as a tarball
                        instead of as a folder structure in the target
                        location
  -s, --includesources  Add this flag for output bundles to include the full
                        source tree.
  -t THREADS, --threads THREADS
                        Define a limit on the number of threads that make is
                        allowed to use.

logging options:
  -l, --savelog         Add this flag to save the build log to a file in the
                        logs/ directory.
  -d, --debugmessages   Add this flag to enable printing verbose debug
                        messages.
  -p, --printcommands   Add this flag to print bash/batch commands run by
                        installSynApps.
"""

# Support python modules
import json
import os
import argparse
from pathlib import Path
import shutil
import sys
import time

from installSynApps import logger

# InstallSynAppsModules
from . import get_welcome_text, CONFIG_DIR
from .data_model import InstallConfiguration, InstallModule
from .utils import get_active_environment, DEFAULT_MACROS, DEFAULT_MODULES, get_module_configure_dirs
from .errors import *
from .clone import clone_and_checkout_config, clone_single_module
from .build import build_all, build_single_module


def show_prompt(text: str, default: str=None, choices: list[str]=None, display_choices_inline: bool=False, return_resp_as_index: bool=False):

    if default is not None and type(default) == int:
        default = choices[default]

    if choices is not None and default is not None and default not in choices:
        raise KeyError(f"Default value of {default} not in specified choice list!")

    txt_to_print = text
    if display_choices_inline:
        txt_to_print += f' ({"/".join(choices)}) |'

    if default is not None:
        txt_to_print += f" [{default}]"
    txt_to_print += " > "

    valid = False
    ret = None
    while not valid:
        if choices is not None and not display_choices_inline:
            for i, choice in enumerate(choices):
                print(f"    {i+1}. {choice}")
            print()
        ret = input(txt_to_print)

        # First case - empty selection. If default is set, use that, otherwise error.
        if len(ret) == 0:
            if default is not None:
                ret = default
                valid = True
            else:
                print("Selection cannot be empty!\n")
        else:
            # Either we don't have specified choices, or ret must be in choices
            if choices is None or ret in choices:
                valid = True
            else:
                # If ret is not in choices, check if it is an int and
                # if it is within the range of choice indexes.
                try:
                    if int(ret) in range(1, len(choices) + 1):
                        ret = choices[int(ret) - 1]
                        valid = True
                    else:
                        raise ValueError(
                            "Selection by number cannot be outside valid range!"
                        )
                except ValueError:
                    print(f"Selected option {ret} is invalid!\n")

    print(f"Selected option: {ret}\n")

    # Return index of choice if specified
    if return_resp_as_index and choices is not None:
        for i, choice in enumerate(choices):
            if choice == ret:
                ret = i
                break

    return ret


def parse_args():
    parser = argparse.ArgumentParser(description="Utility for managing EPICS build environments.")
    parser.add_argument("command", help="Primary action", choices=["init", "delete", "clone", "build", "update", "use", "show", "help"])
    parser.add_argument("subcommand", nargs="+", help="First subcommand must be in [env, module]. Subsequent subcommand is either the env config path or module name.")
    parser.add_argument("-t", "--threads", help="Number of threads to use for build", type=int, default=0)

    parser.add_argument("-d", "--debug", help="Enable debug messages", action="store_true")
    parser.add_argument("-p", "--printcommands", help="Print bash/batch commands run by epicsenv", action="store_true")
    parser.add_argument("-c", "--config", help="Path to environment config file")

    parser.add_argument("-u", "--url", help="Module git repository url")
    parser.add_argument("-v", "--version", help="Module version to checkout")
    parser.add_argument("-r", "--recursive", help="Clone module recursively", action="store_true")

    args = vars(parser.parse_args())
    if len(args["subcommand"]) == 2:
        args["target"] = args["subcommand"][1]
    elif len(args["subcommand"]) == 1:
        args["target"] = None
    else:
        raise ValueError("Invalid number of subcommands provided, must be 1 or 2.")

    return args


def init_env(args):
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
        with open(os.path.join(CONFIG_DIR, "epicsenv.ini"), "w") as fp:
            fp.write("ACTIVE_ENV=\n")

    env_location = show_prompt("Initialize local environment?", choices=["local", "global"], default="local")

    env = {}
    if env_location == "local":
        os.mkdir("epicsenv")
        env["NAME"] = "epicsenv"
        top_dir = os.path.join(os.getcwd(), "epicsenv")
        env_config_path = os.path.join(top_dir, "epicsenv.json")
    else:
        env["NAME"] = show_prompt("Name of the environment to initialize.", default="epicsenv")
        top_dir = os.getcwd()
        env_config_path = os.path.join(CONFIG_DIR, f"{env['NAME']}.json")

    env["BUILD_LOC"] = show_prompt("Path to the build location", default=os.path.join(top_dir, "build"))
    env["INSTALL_LOC"] = show_prompt("Path to the install location", default=os.path.join(top_dir, "install"))
    start_with_defaults = show_prompt("Start with default EPICS_BASE and SUPPORT modules?", choices=["y", "n"], default="y")
    if start_with_defaults == "y":
        env["CONFIG_MACROS"] = DEFAULT_MACROS
        env["MODULES"] = DEFAULT_MODULES

    with open(env_config_path, "w") as fp:
        env_as_json = json.dumps(env, indent=4)
        fp.write(env_as_json)

    print(f"Environment {env['NAME']} initialized with config file at {env_config_path}.")
    print(f"Activate with: epicsenv activate env {env['NAME']}")


def use_env(args) -> Path | None:
    if args['target'] is None and os.path.exists(os.path.join("epicsenv", "epicsenv.json")):
        epics_env_config_path = os.path.abspath(os.path.join("epicsenv", "epicsenv.json"))
    elif os.path.exists(args['target']) and os.path.isfile(args['target']) and args['target'].endswith(".json"):
        epics_env_config_path = os.path.abspath(args['target'])
    else:
        epics_env_config_path = os.path.join(CONFIG_DIR, f"{args['target']}.json")
    try:
        InstallConfiguration(epics_env_config_path)
        with open(os.path.join(CONFIG_DIR, "epicsenv.ini"), "w") as fp:
            fp.write(f"ACTIVE_ENV={epics_env_config_path}\n")
        print(f"Environment {epics_env_config_path} activated.")
        return Path(epics_env_config_path)

    except Exception as e:
        print(f"Failed to activate environment {epics_env_config_path}!")
        print(str(e))

    return None


def delete_env(args):
    if args['target'] is None:
        raise ValueError("No target environment specified for deletion.")

    current_active_env = get_active_environment()

    active_env = use_env(args)
    InstallConfiguration(active_env)

    if os.path.exists(active_env):
        os.remove(active_env)
        print(f"Environment {active_env} deleted.")
    else:
        print(f"Environment {active_env} not found.")

    if current_active_env != active_env:
        with open(os.path.join(CONFIG_DIR, "epicsenv.ini"), "w") as fp:
            fp.write(f"ACTIVE_ENV={current_active_env}\n")

def clone_env(args):
    active_env = get_active_environment()
    if args['target'] is not None and active_env is None:
        active_env = use_env(args)
    if active_env is None:
        raise NoActiveEnvironmentError("No active environment to clone.")

    failed_to_clone = clone_and_checkout_config(InstallConfiguration(active_env))
    if len(failed_to_clone) > 0:
        print("Failed to clone the following modules:")
        for mod in failed_to_clone:
            print(f"  - {mod}")
    else:
        print("Environment cloned and checked out.")


def build_env(args):
    active_env = get_active_environment()
    if args['target'] is not None and get_active_environment() is None:
        active_env = use_env(args)
    if active_env is None:
        raise NoActiveEnvironmentError("No active environment to clone.")
    env = InstallConfiguration(active_env)
    build_all(env, num_threads=args["threads"])
    env.save()
    print("Environment built.")


def show_env(args):
    active_env = get_active_environment()

    print("Available environments:\n")
    if os.path.exists(CONFIG_DIR):
        for env in os.listdir(CONFIG_DIR):
            if env.endswith(".json"):
                print(f"  - {env.split('.')[0]}\n")
    if os.path.exists(os.path.join("epicsenv", "epicsenv.json")):
        print("  - local environment")

    if active_env is None:
        print("\nNo active environment. Use 'epicsenv use env <env_name>' to activate one.")
    else:
        print("  - active environment\n")
        print("Currently active environment:")
        print(InstallConfiguration(active_env))


def build_module(args):
    active_env = get_active_environment()
    if args['target'] is None:
        raise ValueError("No target module specified for build.")
    if active_env is None:
        raise NoActiveEnvironmentError("No active environment to build module.")

    env = InstallConfiguration(active_env)
    if args['target'] not in env.modules:
        raise ValueError(f"Module {args['target']} not found in active environment! Add it first")

    build_single_module(env, env.modules[args['target']], num_threads=args["threads"])
    env.save()

def clone_module(args):
    active_env = get_active_environment()
    if args['target'] is None:
        raise ValueError("No target module specified for cloning.")
    if active_env is None:
        raise NoActiveEnvironmentError("No active environment to build module.")
    env = InstallConfiguration(active_env)
    if args['target'] not in env.modules:
        raise ValueError(f"Module {args['target']} not found in active environment! Add it first")
    clone_single_module(env.build_location, env.modules[args['target']])


def update_env(args):
    active_env = get_active_environment()
    if args['target'] is not None and active_env is None:
        use_env(args)
    if active_env is None:
        raise NoActiveEnvironmentError("No active environment to update.")
    env = InstallConfiguration(active_env)
    env.auto_update_modules()
    env.save()

def update_module(args):
    active_env = get_active_environment()
    if args['target'] is None:
        raise ValueError("No target module specified for update.")
    if active_env is None:
        raise NoActiveEnvironmentError("No active environment to update module.")
    env = InstallConfiguration(active_env)
    if args['target'] not in env.modules:
        raise ValueError(f"Module {args['target']} not found in active environment! Add it first")
    env.auto_update_module_tag(env.modules[args['target']])
    env.save()


def init_module(args):
    active_env = get_active_environment()
    if args['target'] is not None and active_env is None:
        use_env(args)
    if active_env is None:
        raise NoActiveEnvironmentError("No active environment to add module.")
    env = InstallConfiguration(active_env)

    name = show_prompt("Name of the module", default="NEW_MODULE")
    mod_config  = {}
    mod_config["URL"] = show_prompt("Git URL where the module can be downloaded from.")
    mod_config["VERSION"] = show_prompt("Version of the module to checkout.", default="main")
    mod_config["RECURISVE"] = show_prompt("Clone recursively?", choices=['y', 'n'], default="n")
    mod_config["DEPS"] = []
    mod_config["STATE"] = 0
    env.modules[name] = InstallModule(name, mod_config[name])
    env.save()

def use_module(args):
    if args["target"] is None:
        target = os.getcwd()
    
    active_env = get_active_environment()
    if active_env is None:
        raise NoActiveEnvironmentError("No active environment to point module to.")
    env = InstallConfiguration(active_env)

    for configure_dir, filenames in get_module_configure_dirs(target):
        for file in filenames:
            if file.startswith("CONFIG_SITE") or file.startswith("RELEASE"):
                os.remove(os.path.join(configure_dir, file))
        with open(os.path.join(configure_dir, "CONFIG_SITE"), "w") as fp:
            for macro in env.build_options:
                fp.write(f"{macro}={env.build_options[macro]}\n")
        with open(os.path.join(configure_dir, "RELEASE"), "w") as fp:
            for mod in env.modules.values():
                fp.write(f"{mod.name}={os.path.join(env.build_location, mod.url.split('/')[-1].split('.')[0])}\n")

def main():

    print(get_welcome_text())
    args = parse_args() # Get CLI args
    logger._DEBUG = args["debug"] # Set debug flag
    logger._PRINT_COMMANDS = args["printcommands"] # Set print commands flag

    # Cleverly get function name by concatenating command and subcommand, and run with args
    func = getattr(sys.modules[__name__], f"{args['command']}_{args['subcommand'][0]}")
    func(args)


if __name__ == "__main__":
    main()

