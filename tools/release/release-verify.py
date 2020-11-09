#!/usr/bin/env python3
import subprocess
import sys
import argparse
import os
import zipfile
from github import Github
import yaml
import requests
from requests.auth import HTTPBasicAuth

# Directories where the library submodules exist.
CSDK_LIBRARY_DIRS = [os.path.join("libraries", "aws"), os.path.join("library", "standard")]

# The only branches allowed on the CSDK repo.
CSDK_BRANCHES = ["master", "v4_beta_deprecated"]


CSDK_ORG = "sarenameas"
CSDK_REPO = "aws-iot-device-sdk-embedded-c"
GITHUB_API_URL = "https://api.github.com"
GITHUB_ACCESS_TOKEN = ""
GITHUB_AUTH_HEADER = {"Authorization": "token %s" % GITHUB_ACCESS_TOKEN, "Accept": "application/vnd.github.v3+json"}
JENKINS_API_URL = "https://amazon-freertos-ci.corp.amazon.com/"
JENKINS_USERNAME = ""
JENKINS_PASSWORD = ""
JENKINS_CSDK_DEMOS_PATH = "/job/csdk/job/demo_pipeline/lastBuild/api/json"
JENKINS_CSDK_TESTS_PATH = "/job/csdk/job/nightly/lastBuild/api/json"
JENKINS_AUTH_HEADER = {"Authorization": "Basic %s:%s" % (JENKINS_USERNAME, JENKINS_PASSWORD)}


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


def validate_manifest(csdk_root, csdk_version, lib_versions):
    """
    Validates the manifest.yml file at the root of the CSDK.
    Args:
        csdk_root (str): The root of the CSDK repo.
        csdk_versions (str): The new version of the CSDK repo.
        lib_versions (dict): A dictionary containing the new versions of each library.
        Please see tools/release/config.yml.
    """
    with open(os.path.join(csdk_root, "manifest.yml")) as manifest_file:
        manifest = yaml.load(manifest_file, Loader=yaml.FullLoader)

    manifest_version = manifest["version"]
    if manifest_version != csdk_version:
        raise Exception(f"FAIL: Invalid manifest.yml. CSDK version {manifest_version} should be {csdk_version}.")

    for library in lib_versions.keys():
        found = filter(lambda dep: dep["name"].casefold() == library, manifest["dependencies"])
        found = list(found)
        if len(found) != 1:
            raise Exception(
                f"FAIL: Invalid manifest.yml. Found {len(found)} occurrences of required library {library}."
            )

        dep_version = found[0]["version"]
        dep_name = found[0]["name"]
        if dep_version != lib_versions[library]:
            raise Exception(f"FAIL:Invalid manifest.yml. Invalid version {dep_version} for {dep_name}")
    print("PASS: manifest.yml contains all libraries and their versions.")


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
    with open(os.path.join(csdk_root, "tools", "release", "config.yml")) as config_file:
        configs = yaml.load(config_file, Loader=yaml.FullLoader)

    # Verify that Manifest.yml has all libraries and their versions.
    validate_manifest(csdk_root, configs["csdk_version"], configs["versions"])

    # Check that release-candidate is created. I think it's a bit much for the
    # script to create release-candidate for you. I think that should be part of
    # the CM, so that it is more intentional.
    access_token = os.environ.get("GITHUB_ACCESS_TOKEN")
    if access_token == None:
        access_token = configs["github_access_token"]
    if access_token == None:
        raise Exception("Please define GITHUB_ACCESS_TOKEN in your system's environment variables or in config.yml")
    GITHUB_ACCESS_TOKEN = access_token
    JENKINS_USERNAME = configs["jenkins_username"]
    JENKINS_PASSWORD = configs["jenkins_password"]

    git = Github(access_token)
    git_repo = git.get_organization(CSDK_ORG).get_repo(CSDK_REPO)

    # Update the library submodules to the latest. A PR will need to be created for this.
    # TODO: Consider taking this out. This might need to be a CM step so it is
    # more intentional.
    run_cmd("git submodule update --remote libraries/aws/* libraries/standard/*")

    # Check that all GHA actions pass in all libraries.
    # Github actions support is not officially released yet in pygithub. We must
    # use the REST API.
    # https://api.github.com/repos/freertos/corehttp/actions/runs?branch=master Checks all GHA runs on the master branch.
    # https://api.github.com/repos/freertos/corehttp/commits/master/check-runs Checks ALL checks GHA
    # https://api.github.com/repos/freertos/corehttp/commits/master/status Checks the status of CBMA and other non GHA checks
    for repo in config["versions"].keys():
        gha_req = requests.get(f"{GITHUB_API_URL}/{repo}/commits/master/check-runs", headers=GITHUB_AUTH_HEADER)
        # The first item is the latest commit on master.
        if gha_req.json()["check_runs"][0]["conclusion"] != "success":
            raise Exception(f"The GHA status checks failed for {repo}.")
        gha_req = requests.get(f"{GITHUB_API_URL}/{repo}/commits/master/status", headers=GITHUB_AUTH_HEADER)
        if gha_req.json()["state"] != "success":
            raise Exception(f"The CBMC status checks failed for {repo}.")

    # Check a repo that only qualified branches exist
    jenkins_req = requests.get(f"{JENKINS_API_URL}/{JENKINS_CSDK_DEMOS_PATH}", auth=HTTPBasicAuth(JENKINS_USERNAME, JENKINS_PASSWORD))
    if jenkins_req.json()["result"] != "SUCCESS":
        raise Exception(f"Jenkins job {JENKINS_API_URL}/{JENKINS_CSDK_DEMOS_PATH} failed.")
    jenkins_req = requests.get(f"{JENKINS_API_URL}/{JENKINS_CSDK_TESTS_PATH}", auth=HTTPBasicAuth(JENKINS_USERNAME, JENKINS_PASSWORD))
    if jenkins_req.json()["result"] != "SUCCESS":
        raise Exception(f"Jenkins job {JENKINS_API_URL}/{JENKINS_CSDK_TESTS_PATH} failed.")

    

    # Tag each of the library repos.

    # Verify submodules point to each of the new tags.

    None


if __name__ == "__main__":
    main()
