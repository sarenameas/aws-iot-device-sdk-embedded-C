#!/usr/bin/env python3
import subprocess
import argparse
import os
import yaml
import requests
import logging
from requests.auth import HTTPBasicAuth

# Directories where the library submodules exist.
CSDK_LIBRARY_DIRS = ["libraries/aws", "libraries/standard"]

# The only branches allowed on the CSDK repo.
CSDK_BRANCHES = ["master", "v4_beta_deprecated"]

# CSDK organization and repo constants
CSDK_ORG = "aws"
CSDK_REPO = "aws-iot-device-sdk-embedded-c"

# Github API global. The Github API us used instead of pyGithub because some
# checks are not available yet in the packet.
GITHUB_API_URL = "https://api.github.com"
GITHUB_ACCESS_TOKEN = ""
GITHUB_AUTH_HEADER = {"Authorization": "token {}", "Accept": "application/vnd.github.v3+json"}

# Jenkins API globals
JENKINS_API_URL = "https://amazon-freertos-ci.corp.amazon.com"
JENKINS_USERNAME = ""
JENKINS_PASSWORD = ""
JENKINS_CSDK_DEMOS_PATH = "job/csdk/job/demo_pipeline/lastCompletedBuild"
JENKINS_CSDK_TESTS_PATH = "job/csdk/job/nightly/lastCompletedBuild"
JENKINS_API_PATH = "api/json"
JENKINS_SERVER_VERIFY = True

# Errors found in this run.
errors = 0


def log_error(error_log):
    global errors
    logging.error(error_log)
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
    for library_dir in CSDK_LIBRARY_DIRS:
        # Get the submodules in the library directory.
        git_req = requests.get(
            f"{GITHUB_API_URL}/repos/{CSDK_ORG}/{CSDK_REPO}/contents/{library_dir}?ref=release-candidate",
            headers=GITHUB_AUTH_HEADER,
        )
        # A 404 status code means the branch doesn't exist.
        if git_req.status_code == 404:
            log_error(
                "The release-candidate branch does not exist in the CSDK. Please create the release-candidate branch."
            )
            break
        else:
            # For each library submodule in this directory get the status checks results.
            for library in git_req.json():
                library_name = library["name"]
                # Get the commit SHA of the branch currently in release-candidate.
                git_req = requests.get(
                    f"{GITHUB_API_URL}/repos/{CSDK_ORG}/{CSDK_REPO}/contents/{library_dir}/{library_name}?ref=release-candidate",
                    headers=GITHUB_AUTH_HEADER,
                )
                commit_sha = git_req.json()["sha"]
                # Get the organization of this repo
                html_url = git_req.json()["html_url"]
                start_index = html_url.find(".com/") + len(".com/")
                end_index = html_url.find("/tree")
                repo_path = html_url[start_index:end_index]
                # Get the status of the CBMC checks
                git_req = requests.get(
                    f"{GITHUB_API_URL}/repos/{repo_path}/commits/{commit_sha}/status", headers=GITHUB_AUTH_HEADER
                )
                if git_req.json()["state"] != "success":
                    log_error(f"The CBMC status checks failed for {html_url}.")
                # Get the status of the GHA checks
                git_req = requests.get(
                    f"{GITHUB_API_URL}/repos/{repo_path}/commits/{commit_sha}/check-runs", headers=GITHUB_AUTH_HEADER
                )
                for check_run in git_req.json()["check_runs"]:
                    if check_run["conclusion"] != "success":
                        check_run_name = check_run["name"]
                        log_error(f"The GHA {check_run_name} check failed for {html_url}.")


def validate_ci():
    """
    Validates that all CSDK jobs in the Jenkins CI passed.
    """
    jenkins_req = requests.get(
        f"{JENKINS_API_URL}/{JENKINS_CSDK_DEMOS_PATH}/{JENKINS_API_PATH}",
        auth=HTTPBasicAuth(JENKINS_USERNAME, JENKINS_PASSWORD),
        verify=JENKINS_SERVER_VERIFY,
    )
    if jenkins_req.json()["result"] != "SUCCESS":
        log_error(f"Jenkins job failed: {JENKINS_API_URL}/{JENKINS_CSDK_DEMOS_PATH}.")
    jenkins_req = requests.get(
        f"{JENKINS_API_URL}/{JENKINS_CSDK_TESTS_PATH}/{JENKINS_API_PATH}",
        auth=HTTPBasicAuth(JENKINS_USERNAME, JENKINS_PASSWORD),
        verify=JENKINS_SERVER_VERIFY,
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
        git_req = requests.get(f"{GITHUB_API_URL}/repos/{repo_path}/branches", headers=GITHUB_AUTH_HEADER)
        valid_branches = ["master"]
        if repo_path == f"{CSDK_ORG}/{CSDK_REPO}":
            valid_branches += ["v4_beta_deprecated", "release-candidate"]
        for branch in git_req.json():
            branch_name = branch["name"]
            if branch_name not in valid_branches:
                log_error(f"Invalid branch {branch_name} found in {repo_path}.")


def validate_release_candidate_branch():
    """
    Verifies there are no pending PRs to the release candidate branch.
    """
    git_req = requests.get(
        f"{GITHUB_API_URL}/repos/{CSDK_ORG}/{CSDK_REPO}/pulls?base=release-candidate", headers=GITHUB_AUTH_HEADER
    )
    if len(git_req.json()) == 0:
        logging.warn("release-candidate branch does not exist in CSDK.")
    for pr in git_req.json():
        pr_url = pr["url"]
        log_error(f"Pull request to release-candidate {pr_url}.")


def set_globals(configs):
    global GITHUB_ACCESS_TOKEN
    global GITHUB_AUTH_HEADER
    global JENKINS_USERNAME
    global JENKINS_PASSWORD
    global JENKINS_SERVER_VERIFY

    access_token = os.environ.get("GITHUB_ACCESS_TOKEN")
    if access_token == None:
        access_token = configs["github_access_token"]
    if access_token == None:
        raise Exception("Please define GITHUB_ACCESS_TOKEN in your system's environment variables or in config.yml")
    GITHUB_ACCESS_TOKEN = access_token
    GITHUB_AUTH_HEADER["Authorization"] = GITHUB_AUTH_HEADER["Authorization"].format(GITHUB_ACCESS_TOKEN)
    JENKINS_USERNAME = configs["jenkins_username"]
    JENKINS_PASSWORD = configs["jenkins_password"]
    JENKINS_SERVER_VERIFY = False if configs["disable_jenkins_server_verify"] else True


def main():
    """
    Performs pre-release validation of the CSDK and the library spoke repos.
    """
    # Parse the input arguments to this script.
    parser = argparse.ArgumentParser(description="Perform CSDK Release activities.")
    parser.add_argument("-r", "--root", action="store", required=True, dest="root", help="CSDK repo root path.")
    parser.add_argument(
        "--disable-jenkins-server-verify",
        action="store_true",
        required=False,
        default=False,
        dest="disable_jenkins_server_verify",
        help="Disable server verification for the Jenkins API calls if your system doesn't have the certificate in its store.",
    )
    args = parser.parse_args()
    csdk_root = os.path.abspath(args.root)

    # Parse the input config.yml
    with open(os.path.join(csdk_root, "tools", "release", "config.yml")) as config_file:
        configs = yaml.load(config_file, Loader=yaml.FullLoader)
    configs["disable_jenkins_server_verify"] = args.disable_jenkins_server_verify

    # Parse the manifest.yml
    with open(os.path.join(csdk_root, "manifest.yml")) as manifest_file:
        manifest = yaml.load(manifest_file, Loader=yaml.FullLoader)
    repo_paths = []
    for dep in manifest["dependencies"]:
        dep_url = dep["repository"]["url"]
        repo_paths.append(dep_url[dep_url.find(".com/") + len(".com/") :])
    repo_paths.append(f"{CSDK_ORG}/{CSDK_REPO}")

    # Get the authentication variables
    set_globals(configs)

    # Create results file to write to.
    logging.basicConfig(filename="errors.log", filemode="w", level=logging.ERROR)

    # Verify that Manifest.yml has all libraries and their versions.
    validate_manifest(manifest, configs["csdk_version"], configs["versions"])

    # Verify status checks in all repos.
    validate_checks(repo_paths)

    # Validate that the jenkins CI passed.
    validate_ci()

    # Check a repo that only qualified branches exist
    validate_branches(repo_paths)

    # Verify there are no pending PRs to the release-candidate branch.
    validate_release_candidate_branch()

    if errors > 0:
        print("Release verification failed please see errors.log")
    else:
        print("All release verification passed.")


if __name__ == "__main__":
    main()
