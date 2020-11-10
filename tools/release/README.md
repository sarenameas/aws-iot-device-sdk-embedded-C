# Release automation for AWS IoT Embedded C SDK

## Prerequisites

- Linux environment
- [Git](https://git-scm.com/downloads/)
- [Python 3](https://www.python.org/downloads/)

This script accompanies the CSDK release CM. You must use it in conjunction with a Preflight step.

## Output
This script checks that:
    - All unit tests and code quality checks pass in each library repo committed on the release-candidate branch.
    - All jobs pass https://amazon-freertos-ci.corp.amazon.com/view/CSDK%20Jobs/job/csdk/
    - Only the master branch exists in library repos.
    - Only the master branch and v4_beta_deprecated exist in the CSDK.
    - manifest.yml has all libraries and versions expected in this script's config.yml
    - 

This script outputs:
    - **error.log** in the working directory for any errors found in verification.
    - **docs_to_review.txt** for all CHANGELOG.md and README.md files to review.

## Usage

1. Clone https://github.com/aws/aws-iot-device-sdk-embedded-C/
```console
git clone git@github.com:aws/aws-iot-device-sdk-embedded-C.git --recurse-submodules
```
1. Enter your [Github API Access Token](https://docs.github.com/en/free-pro-team@latest/github/authenticating-to-github/creating-a-personal-access-token) in [config.yml](config.yml).
```yml
github_access_token: abcdefghijklmnopqrztuvwxyz12345678910111
```

1. Enter your username and password to the Jenkins CI into [config.yml](config.yml).
```yml
jenkins_username: <AMAZON_LOGIN>
jenkins_password: <JEKINS_PASSWORD>
```

1. Enter the versions for the next release into [config.yml](config.yml).
```yml
csdk_version: "202012.00"
versions:
  coremqtt: "v1.0.1"
  corejson: "v2.0.0"
  device-shadow-for-aws-iot-embedded-sdk: "v1.0.1"
  corehttp: "v1.0.0"
  device-defender-for-aws-iot-embedded-sdk: "v1.0.0"
  jobs-for-aws-iot-embedded-sdk: "v1.0.0"
```

1. Run this script with the root of the CSDK repo.
```console
python3 release-verify.py --root <CSDK_ROOT>
```

