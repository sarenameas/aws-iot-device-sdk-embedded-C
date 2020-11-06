#!/usr/bin/env python3
import subprocess
import sys
import argparse
import os
import zipfile
import github
import yaml

# Directories where the library submodules exist.
CSDK_LIBRARY_DIRS = [ os.path.join("libraries", "aws"),
                      os.path.join("library", "standard") ]

# The only branches allowed on the CSDK repo.
CSDK_BRANCHES = [ "master",
                  "v4_beta_deprecated"]

def run_cmd(cmd):
    """
    Execute the input command on the shell.
    """
    print(f"Executing command: {cmd}")
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
            encoding="utf-8",
            check=True,
            timeout=180,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        result = e.stdout
        return result


# TODO: Create rollback function.

def validate_manifest(csdk_root, versions):
    """
    Validates the manifest.yml file at the root of the CSDK.
    Args:
        csdk_root (str): The root of the CSDK repo.
        versions (dict): A dictionary containing the versions of each library.
        Please see tools/release/config.yml.
    """
    with open(os.path.join(csdk_root,"manifest.yml")) as manifest_file:
        manifest = yaml.load(manifest_file, Loader=yaml.FullLoader)

    for library in versions.keys():
        found = filter(lambda dep: dep["name"].casefold() == library, manifest["dependencies"])
        found = list(found)
        if len(found) != 1:
            raise Exception(f"Invalid manifest.yml. Found {len(found)} occurrences of required library {library}.")

        dep_version = found[0]["version"]
        dep_name = found[0]["name"]
        if dep_version != versions[library]:
            raise Exception(f"Invalid manifest.yml. Invalid version {dep_version} for {dep_name}")

def main():
    """
    Update the CSDK and its library repos for release.
    """

    # Options:
    parser = argparse.ArgumentParser(description="Perform CSDK Release activities.")
    parser.add_argument("-r", "--root", action="store", required=True, dest="root", help="CSDK repo root path.")

    args = parser.parse_args()
    csdk_root = os.path.abspath(args.root)

    # Parse the input config.yml
    with open(os.path.join(csdk_root,"tools","release","config.yml")) as config_file:
        configs = yaml.load(config_file, Loader=yaml.FullLoader)

    # Verify that Manifest.yml has all libraries and their versions.
    validate_manifest(csdk_root, configs["versions"])

    # Create and checkout the release-candidate branch. Push to origin.
    if run_cmd("git ls-remote --heads git@github.com:aws/aws-iot-device-sdk-embedded-C.git release-candidate") == "":
        run_cmd("git fetch git@github.com:aws/aws-iot-device-sdk-embedded-C.git master:release_master")
        run_cmd("git checkout release_master")
        run_cmd("git checkout -b release-candidate")
        run_cmd("git push git@github.com:aws/aws-iot-device-sdk-embedded-C.git release-candidate")
    else:
        print("Branch release-candidate exists on remote origin.")

    # Update the library submodules to the latest. A PR will need to be created.

    # Check that all GHA actions pass in all libraries.

    # Check a repo that only qualified branches exist

    # Tag each of the library repos.

    # Verify submodules point to each of the new tags.

    None


if __name__ == "__main__":
    main()
