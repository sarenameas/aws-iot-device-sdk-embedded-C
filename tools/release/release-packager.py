#!/usr/bin/env python3
import argparse
import zipfile
import os
import yaml

CSDK_LIBRARY_DIRS = ["libraries/aws", "libraries/standard"]

def main():
    """
    Zip up the CSDK and all of the spoke repos currently in here.
    """
    parser = argparse.ArgumentParser(description="Zip up the CSDK and all of the spoke library repos.")
    parser.add_argument(
        "-r",
        "--root",
        action="store",
        required=True,
        dest="root",
        help="CSDK repo root path."
    )
    parser.add_argument(
        "--github-access-token",
        action="store",
        required=False,
        dest="github_access_token",
        help="Github API developer access token.",
    )

    csdk_root = os.path.abspath(args.root)


if __name__ == "__main__":
    # Get the current versions from the manifest.yml.
    # Tag all repos using the Github API. For each of the libraries in the 
    # Verify 
    main()
