#!/usr/bin/env python3
import subprocess
import argparse
import os
import yaml
import requests
import logging
from requests.auth import HTTPBasicAuth

# Directories where the library submodules exist.
CSDK_LIBRARY_DIRS = [os.path.join("libraries", "aws"), os.path.join("library", "standard")]

# The only branches allowed on the CSDK repo.
CSDK_BRANCHES = ["master", "v4_beta_deprecated"]

# CSDK organization and repo constants
CSDK_ORG = "sarenameas"
CSDK_REPO = "aws-iot-device-sdk-embedded-c"

# Github API global
GITHUB_API_URL = "https://api.github.com"
GITHUB_ACCESS_TOKEN = ""
GITHUB_AUTH_HEADER = {"Authorization": "token %s" % GITHUB_ACCESS_TOKEN, "Accept": "application/vnd.github.v3+json"}

# Jenkins API globals
JENKINS_API_URL = "https://amazon-freertos-ci.corp.amazon.com/"
JENKINS_USERNAME = ""
JENKINS_PASSWORD = ""
JENKINS_CSDK_DEMOS_PATH = "job/csdk/job/demo_pipeline/lastCompletedBuild"
JENKINS_CSDK_TESTS_PATH = "job/csdk/job/nightly/lastCompletedBuild"
JENKINS_API_PATH = "api/json"

# Errors found in this run.
errors = 0

def log_error(error_log):
    global errors
    log_error(error_log)
    errors = errors + 1


def validate_manifest(manifest, csdk_version, lib_versions) -> list:
    """
    Validates the manifest.yml file at the root of the CSDK.
    Args:
        manifest (dict): The CSDK's manifest.yml loaded into a dictionary.
        csdk_versions (str): The new version of the CSDK repo.
        lib_versions (dict): A dictionary containing the new versions of each library.
        Please see tools/release/config.yml.
    Returns the list of errors.
    """
    manifest_version = manifest["version"]
    if manifest_version != csdk_version:
        log_error(f"Invalid manifest.yml. CSDK version {manifest_version} should be {csdk_version}.")

    for library in lib_versions.keys():
        found = filter(lambda dep: dep["name"].casefold() == library, manifest["dependencies"])
        found = list(found)
        if len(found) != 1:
            log_error(f"Invalid manifest.yml. Found {len(found)} occurrences of required library {library}.")
        else:
            dep_version = found[0]["version"]
            dep_name = found[0]["name"]
            if dep_version != lib_versions[library]:
                log_error(f"Invalid manifest.yml. Invalid version {dep_version} for {dep_name}")


def validate_checks(repo_paths):
    """
    Validates that all of the GHA and CBMC status checks passed on all repos.
    Args:
        repo_paths (dict): Paths to all library repos in the CSDK, including their org.
    """
    for repo_path in repo_paths:
        git_req = requests.get(f"{GITHUB_API_URL}/{repo_path}/commits/master/check-runs", headers=GITHUB_AUTH_HEADER)
        # The first item is the latest commit on master.
        if git_req.json()["check_runs"][0]["conclusion"] != "success":
            log_error(f"The GHA status checks failed for {repo_path}.")
        git_req = requests.get(f"{GITHUB_API_URL}/{repo_path}/commits/master/status", headers=GITHUB_AUTH_HEADER)
        if git_req.json()["state"] != "success":
            log_error(f"The CBMC status checks failed for {repo_path}.")


def validate_ci():
    """
    Validates that all CSDK jobs in the Jenkins CI passed.
    """
    jenkins_req = requests.get(
        f"{JENKINS_API_URL}/{JENKINS_CSDK_DEMOS_PATH}/{JENKINS_API_PATH}",
        auth=HTTPBasicAuth(JENKINS_USERNAME, JENKINS_PASSWORD),
    )
    if jenkins_req.json()["result"] != "SUCCESS":
        log_error(f"Jenkins job failed: {JENKINS_API_URL}/{JENKINS_CSDK_DEMOS_PATH}.")
    jenkins_req = requests.get(
        f"{JENKINS_API_URL}/{JENKINS_CSDK_TESTS_PATH}/{JENKINS_API_PATH}",
        auth=HTTPBasicAuth(JENKINS_USERNAME, JENKINS_PASSWORD),
    )
    if jenkins_req.json()["result"] != "SUCCESS":
        log_error(f"Jenkins job failed: {JENKINS_API_URL}/{JENKINS_CSDK_TESTS_PATH}.")


def validate_branches(repo_paths):
    """
    Validates that only the master branch exists on each library repo.
    Args:
        repo_paths (dict): Paths to all library repos in the CSDK, including their org.
    """
    for repo_path in repo_paths:
        git_req = requests.get(f"{GITHUB_API_URL}/{repo_path}/branches/", headers=GITHUB_AUTH_HEADER)
        valid_branches = ["master"]
        if repo_path == "{CSDK_ORG}/{CSDK_REPO}":
            valid_branches.append("v4_beta_deprecated")
        for branch in git_req.json():
            branch_name = branch["name"]
            if branch_name not in valid_branches:
                log_error(f"Invalid branch {branch_name} found in {repo_path}.")


def validate_release_candidate_branches():
    """
    Verifies there are no pending PRs to the release candidate branch.
    """
    git_req = requests.get(
        f"{GITHUB_API_URL}/{CSDK_ORG}/{CSDK_REPO}/pulls?base=release-candidate", headers=GITHUB_AUTH_HEADER
    )
    for pr in git_req.json():
        pr_url = pr["url"]
        log_error(f"Pull request to release-candidate {pr_url}.")


def main():
    """
    Performs pre-release validation of the CSDK and the library spoke repos.
    """
    # Parse the input arguments to this script.
    parser = argparse.ArgumentParser(description="Perform CSDK Release activities.")
    parser.add_argument("-r", "--root", action="store", required=True, dest="root", help="CSDK repo root path.")
    args = parser.parse_args()
    csdk_root = os.path.abspath(args.root)

    # Parse the input config.yml
    with open(os.path.join(csdk_root, "tools", "release", "config.yml")) as config_file:
        configs = yaml.load(config_file, Loader=yaml.FullLoader)

    # Parse the manifest.yml
    with open(os.path.join(csdk_root, "manifest.yml")) as manifest_file:
        manifest = yaml.load(manifest_file, Loader=yaml.FullLoader)
    repo_paths = []
    for dep in manifest["dependencies"]:
        repo_paths.append(dep["url"][dep["url"].find(".com/") + len(".com/")])
    repo_paths.append("{CSDK_ORG}/{CSDK_REPO}")

    # Get the authentication variables
    access_token = os.environ.get("GITHUB_ACCESS_TOKEN")
    if access_token == None:
        access_token = configs["github_access_token"]
    if access_token == None:
        raise Exception("Please define GITHUB_ACCESS_TOKEN in your system's environment variables or in config.yml")
    GITHUB_ACCESS_TOKEN = access_token
    JENKINS_USERNAME = configs["jenkins_username"]
    JENKINS_PASSWORD = configs["jenkins_password"]

    # Create results file to write to.
    logging.basicConfig(filename="errors.log", filempde="w", level=logging.ERROR)

    # Verify that Manifest.yml has all libraries and their versions.
    validate_manifest(manifest, configs["csdk_version"], configs["versions"])

    # Verify status checks in all repos.
    validate_checks(repo_paths)

    # Validate that the jenkins CI passed.
    validate_ci()

    # Check a repo that only qualified branches exist
    validate_branches(repo_paths)

    # Verify there are no pending PRs to the release-candidate branch.
    validate_release_candidate_branches()

    if errors > 0:
        print("Release verification failed please see results.log")
    else:
        print("All release verification passed.")


if __name__ == "__main__":
    main()
