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


# TODO: Create rollback function.

def validate_manifest(csdk_root, versions):
    """
    Validates the manifest.yml file at the root of the CSDK.
    Args:
        csdk_root (str): The root of the CSDK repo.
        versions (dict): A dictionary containing the versions of each library.
        Please see tools/release/config.yml.
    """
    # Parse manifest.yml
    with open(os.path.join(csdk_root,"manifest.yml")) as manifest_file:
        manifest = yaml.load(manifest_file, Loader=yaml.FullLoader)

    for library in versions.keys():
        found = filter(lambda dep: dep["name"].casefold() == library, manifest["dependencies"])
        found = list(found)
        if len(found) != 1:
            raise Exception(f"Invalid manifest.yml. Found {len(found)} occurrences of required {library}.")

        manifest_dep_version = found[0]["version"]

        if manifest_dep_version != versions[library]:
            raise Exception(f"Invalid version {manifest_dep_version} for {library}")

def main():
    """
    Update the CSDK and its library repos for release.
    """

    # Options:
    parser = argparse.ArgumentParser(description="Perform CSDK Release activities.")
    parser.add_argument("-r", "--root", action="store", required=True, dest="root", help="CSDK repo root path.")
    # TODO: create release-candidate?

    args = parser.parse_args()
    csdk_root = os.path.abspath(args.root)

    # Parse the input config.yml
    with open(os.path.join(csdk_root,"tools","release","config.yml")) as config_file:
        configs = yaml.load(config_file, Loader=yaml.FullLoader)

    # Verify that Manifest.yml has all libraries and their versions.
    validate_manifest(csdk_root, configs["versions"])

    # Parse for the last version and the current version. (using manifest.yml)


    # Create and checkout the release-candidate branch. Push to origin.

    # Update the library submodules to the latest. A PR will need to be created.

    # Check that all GHA actions pass in all libraries.

    # Check a repo that only qualified branches exist

    # Tag each of the library repos.

    # Verify submodules point to each of the new tags.

    None


if __name__ == "__main__":
    main()
