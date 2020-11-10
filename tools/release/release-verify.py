#!/usr/bin/env python3
import subprocess
import argparse
import os
import yaml
import requests
import logging
from requests.auth import HTTPBasicAuth
import re

# Directories where the library submodules exist.
CSDK_LIBRARY_DIRS = ["libraries/aws", "libraries/standard"]

# CSDK organization and repo constants
CSDK_ORG = "aws"
CSDK_REPO = "aws-iot-device-sdk-embedded-c"

# Github API global. The Github API is used instead of pyGithub because some
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
    docs_file = open("docs_to_review.txt", "w+")
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
            # For each library submodule in this directory, get the status checks results and docs to review.
            for library in git_req.json():
                library_name = library["name"]
                # Get the commit SHA of the branch currently in release-candidate.
                commit_sha = library["sha"]
                # Get the organization of this repo
                html_url = library["html_url"]
                repo_path = re.search("(?<=\.com/)(.*)(?=/tree)", html_url).group(0)

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

                # Collect the HTML URLS for reviewing the docs.
                html_url = html_url.split(commit_sha)[0] + "master"
                docs_file.write(f"{library_name}\n")
                docs_file.write(f"{html_url}/README.md\n")
                docs_file.write(f"{html_url}/CHANGELOG.md\n\n")
    docs_file.close()


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


def get_configs(args) -> (dict, str):
    """
    Retrieve configs.yml into a dictionary and get the csdk_root from the the
    input user args.
    Args:
        args(Namespace) User argument namespace.
    """
    csdk_root = os.path.abspath(args.root)
    with open(os.path.join(csdk_root, "tools", "release", "config.yml")) as config_file:
        configs = yaml.load(config_file, Loader=yaml.FullLoader)
    configs["disable_jenkins_server_verify"] = args.disable_jenkins_server_verify
    return (configs, csdk_root)


def get_manifest(csdk_root) -> (dict, list):
    """
    Retrieve manifest.yml into a dictionary. From the manifest.yml we also get
    the org/repo of each library.
    Args:
        csdk_root(str): The absolute path 
    """
    with open(os.path.join(csdk_root, "manifest.yml")) as manifest_file:
        manifest = yaml.load(manifest_file, Loader=yaml.FullLoader)
    repo_paths = []
    for dep in manifest["dependencies"]:
        dep_url = dep["repository"]["url"]
        repo_paths.append(re.search("(?<=\.com/)(.*)", dep_url).group(0))
    repo_paths.append(f"{CSDK_ORG}/{CSDK_REPO}")
    return (manifest, repo_paths)


def set_globals(configs):
    """
    Set global variables used in this script.
    """
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
    jenkins_username = os.environ.get("JENKINS_USERNAME")
    if jenkins_username == None:
        jenkins_username = configs["jenkins_username"]
    if jenkins_username == None:
        raise Exception("Please define JENKINS_USERNAME in your system's environment variables or in config.yml")
    jenkins_password = os.environ.get("JENKINS_USERNAME")
    if jenkins_password == None:
        jenkins_password = configs["jenkins_password"]
    if jenkins_password == None:
        raise Exception("Please define JENKINS_PASSWORD in your system's environment variables or in config.yml")
    GITHUB_ACCESS_TOKEN = access_token
    GITHUB_AUTH_HEADER["Authorization"] = GITHUB_AUTH_HEADER["Authorization"].format(GITHUB_ACCESS_TOKEN)
    JENKINS_USERNAME = jenkins_username
    JENKINS_PASSWORD = jenkins_password
    JENKINS_SERVER_VERIFY = False if configs["disable_jenkins_server_verify"] else True


def parse_arguments() -> argparse.Namespace:
    """
    Parse the input user arguments and return a Namespace.
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
    return parser.parse_args()


def main():
    """
    Performs pre-release validation of the CSDK and the library spoke repos.
    """

    args = parse_arguments()

    # Parse the input config.yml and args for the CSDK root.
    (configs, csdk_root) = get_configs(args)

    # Parse the manifest.yml for org/repo paths.
    (manifest, repo_paths) = get_manifest(csdk_root)

    # Set the authentication variables.
    set_globals(configs)

    # Create error.log to write errors to.
    logging.basicConfig(filename="errors.log", filemode="w", level=logging.ERROR)

    # Verify that Manifest.yml has all libraries and their versions.
    validate_manifest(manifest, configs["csdk_version"], configs["versions"])

    # Verify status checks in all repos.
    validate_checks(repo_paths)

    # Validate that the Jenkins CI passed.
    validate_ci()

    # Check that only qualified branches exist in each library repo.
    validate_branches(repo_paths)

    # Verify there are no pending PRs to the release-candidate branch.
    validate_release_candidate_branch()

    if errors > 0:
        print("Release verification failed, please see errors.log")
    else:
        print("Release verification passed.")


if __name__ == "__main__":
    main()
