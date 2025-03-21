# TCS-GARR Client

![Version](https://img.shields.io/badge/Version-0.19.0-rc.0-brightgreen.svg)

[![python](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
![Contributions welcome](https://img.shields.io/badge/Contributions-Welcome-brightgreen.svg)

## Overview

The `TCS-GARR Client` is a command-line tool for managing and interacting with Harica platform. It offers features like listing, downloading, issuing certificates, approving requests, and generating domain validation tokens, all via the Harica API.

## Warning ⚠️

**Consortium GARR is not affiliated with HARICA, and the present work has not been endorsed by or agreed with HARICA.**

**Consortium GARR provides this code to the community for sharing purposes but does not commit to providing support, maintenance, or further development of the code. Use it at your own discretion.**

### Prerequisites

Before using the TCS-GARR client, please ensure the following:

1. **Create a local account on the Harica platform**: You must create a local account on Harica at [https://cm.harica.gr](https://cm.harica.gr). Do not use federated IDEM credentials, as they do not support API access.

   - If you're already logged in with federated IDEM credentials, you can create a new local account using an email alias. Federated users do not have a password and therefore cannot use the API.

2. **Administrator and Approver Permissions**: To use the API, your local account must have Administrator and Approver permissions. To obtain these:

   - **Enable 2FA (Two-Factor Authentication)** on your profile page.
   - ⚠️⚠️ **Save the TOTP** seed provided after enabling 2FA, as you will need it for future authentication. TOTP seed is like `otpauth://totp/HARICA:...omissis...`
   - After enabling 2FA, request an existing administrator to elevate your account to Administrator and Approver.

Once these steps are completed, you are ready to use the TCS-GARR client.

⚠️ The OTP (One-Time Password) is generated based on the date and time of your PC. If the client fails to authenticate and returns an "Invalid OTP" error, please ensure that your device's date and time are correct and synchronized with a public NTP server.

## Installation

You can install the TCS-GARR client in a virtual environment using `pip` or via `pipx`.

### Virtual Environment

1. Open a terminal or command prompt and navigate to the directory where you want to install the package. Then, run the following command to create a virtual environment:

    ```bash
    mkdir <path>
    python -m venv venv
    ```

    This will create a folder named `venv` in your project directory, containing a self-contained Python environment.

2. Activate the virtual environment based on your operating system:

    ```bash
    source venv/bin/activate
    ```

3. Install the package

    ```bash
    pip install tcs-garr
    ```

### Pipx

1. Open a terminal and install the package

    ```bash
    PIPX_BIN_DIR=/usr/local/bin pipx install tcs-garr
    ```

## Configuration

After installation, the first time you run the client, you will need to initialize the configuration file with your credentials by running:

```bash
tcs-garr init
```

This will create a `tcs-garr.conf` file in your home directory under `.config/tcs-garr` path. This file will contain your Harica username, password, TOTP seed, and folder for issued certificates and will have secure permissions.

If configuration file is not found, system will notify you to initialize the configuration using the `tcs-garr init` command.

## Usage

Once the setup is complete, you can use the TCS-GARR client for various operations. The command syntax follows this pattern:

```bash
tcs-garr [command] [options]
```

To view all available commands and options:

```bash
tcs-garr --help

usage: tcs-garr [-h] [--debug] [--version] [--environment {production,stg}] {approve,cancel,domains,download,init,k8s,list,request,upgrade,validate,whoami} ...

Harica Certificate Manager

positional arguments:
  {approve,cancel,domains,download,init,k8s,list,request,upgrade,validate,whoami}
                        Available commands
    approve             Approve a certificate by ID
    cancel              Cancel a request by ID
    domains             List available domains
    download            Download a certificate by ID
    init                Generate Harica config file
    k8s                 Generate Kubernetes TLS resource file
    list                Generate a report from Harica
    request             Request a new certificate
    upgrade             Self-upgrade command for the app.
    validate            Create validation token for domains
    whoami              Get logged in user profile

options:
  -h, --help            show this help message and exit
  --debug               Enable DEBUG logging.
  --version             show program's version number and exit
  --no-check-release    Skip checking for a new release
  --environment {production,stg}
                        Specify the environment to use (default: production)
```

### Available Commands

All commands are executed on the production environment of Harica at [https://cm.harica.gr](https://cm.harica.gr). By using the `--environment stg` flag, you can execute commands for the staging environment at [https://cm-stg.harica.gr](https://cm-stg.harica.gr).

For example, if you want to use the staging environment, you can initialize the configuration file using the following command:

```bash
tcs-garr --environment stg init
```

⚠️ The OTP (One-Time Password) is generated based on the date and time of your PC. If the client fails to authenticate and returns an "Invalid OTP" error, please ensure that your device's date and time are correct and synchronized with a public NTP server.

1. **Initialize configuration**:

   ```bash
   tcs-garr init
   ```

   This command initializes the configuration file with your credentials (email, password, and TOTP seed).

2. **Get user profile**:

   ```bash
   tcs-garr whoami
   ```

   This command retrieves the profile of the logged-in user.

3. **List all certificates**:

   ```bash
   tcs-garr list --help

   usage: tcs-garr list [-h] [--expired-since EXPIRED_SINCE] [--expiring-in EXPIRING_IN]

   options:
   -h, --help            show this help message and exit
   --expired-since EXPIRED_SINCE
                           List certificates which expiry date is X days before now.
   --expiring-in EXPIRING_IN
                           List certificates which expiry date is X days after now.
   ```

   This command will list all available certificates. You can filter them by date range using the `--expired-since` and `--expiring-in` options.

4. **Download a certificate**:

   ```bash
   tcs-garr download --help

   usage: tcs-garr download [-h] --id ID [--output-filename OUTPUT_FILENAME] [--force] [--download-type {pemBundle,certificate}]

    options:
    -h, --help            show this help message and exit
    --id ID               ID of the certificate to download.
    --output-filename OUTPUT_FILENAME
                            Optional filename to save the certificate inside default output_folder.
    --force, -f           Force overwrite if the output file already exists.
    --download-type {pemBundle,certificate}
                            Type of download: 'pemBundle' or 'certificate'. Default is 'pemBundle'.
   ```

   Replace `ID` with the ID of the certificate you wish to download. You can use `pemBundle` or `certificate` as arguments for specific download formats.

5. **Request a new certificate**:

   ```bash
   tcs-garr request --help

   usage: tcs-garr request [-h] [--profile {OV,DV}] [--wait] (--csr CSR | --cn CN) [--alt_names ALT_NAMES]

   options:
   -h, --help            show this help message and exit
   --profile {OV,DV}     Profile to use between OV or DV. Default: OV
   --wait                Wait for the certificate to be approved
   --csr CSR             Path to an existing CSR file.
   --cn CN               Common name of the certificate.
   --alt_names ALT_NAMES
                           Comma-separated alternative names (only used with --cn).
   ```

   The `request` command is used to submit a new certificate request to Harica.

   You can either provide an existing Certificate Signing Request (`--csr`) or specify the details for generating a new CSR, including the Common Name (`--cn`) and any Subject Alternative Names (`--alt_names`).
   If a new CSR is created using the `--cn` and `--alt_names` options, a private key will also be automatically generated.

   You can choose between the `OV` (OV Profile) or `DV` (DV Profile) profile using the `--profile` option. Default is `OV`.

   After submitting the certificate request, the request must be approved by another Administrator before the certificate can be downloaded. Ensure that an administrator is available to review and approve your request.

   With `--wait`` flag, the command will wait for the certificate to be approved by another administrator. When approved, it will be automatically downloaded.

6. **Approve a certificate**:

   ```bash
   usage: tcs-garr approve [-h] (--id ID | --list-pending | --all)

   options:
   -h, --help      show this help message and exit
   --id ID         ID of the certificates (comma separated) to approve.
   --list-pending  List all pending requests.
   --all           Approve all pending requests.
   ```

   You can list all pending requests using the `--list-pending` option or approve all pending requests using the `--all` option.

   You can also approve a specific certificate by providing its ID using the `--id` option.

7. **Cancel a certificate request**:

   ```bash
   tcs-garr cancel --help

   usage: tcs-garr cancel [-h] --id ID

   options:
   -h, --help  show this help message and exit
   --id ID     ID of the request to cancel.
   ```

   Replace `ID` with the ID of the certificate you wish to cancel.

8. **Generate validation token for domains**:

   ```bash
   usage: tcs-garr validate [-h] --domains DOMAINS

   options:
   -h, --help         show this help message and exit
   --domains DOMAINS  Comma separated list of domains.
   ```

   This command generates validation tokens for the specified domains. Replace `DOMAINS` with a comma-separated list of domains you need to validate.

   To get the list of all available domains in your organization, use the `domains` command.

   ```bash
   tcs-garr domains
   ```

9. **Upgrade package**:

   ```bash
   usage: tcs-garr upgrade [-h]

   options:
   -h, --help  show this help message and exit
   ```

   This command upgrades the package to the latest version.

10. **K8s resource**:

   This command is used to generate a Kubernetes secret YAML file for storing a TLS certificate and its associated private key. The resulting secret can be used in Kubernetes clusters to securely store TLS certificates for applications requiring encrypted communication.

   The command requires the paths to both the certificate file (--cert) and the private key file (--key), as well as the target Kubernetes namespace (--namespace) where the secret will be created.

   ```bash
   usage: tcs-garr k8s [-h] --cert CERT --key KEY --namespace NAMESPACE [--secret-name SECRET_NAME] [--file-name FILE_NAME]

   options:
   -h, --help            show this help message and exit
   --cert CERT           Path to the certificate file.
   --key KEY             Path to the key file.
   --namespace NAMESPACE
                           Kubernetes namespace for the secret.
   --secret-name SECRET_NAME
                           Name for the secret (optional).
   --file-name FILE_NAME
                           Name for the yaml file without the extension (optional).
   ```

## Docker

Docker image is available at GitHub container [registry](https://github.com/ConsortiumGARR/tcs-garr/pkgs/container/tcs-garr).
You can pull them via:

```bash
docker pull ghcr.io/consortiumgarr/tcs-garr:<your_desired_version>
```

### Build

Example of docker image build command:

```bash
docker build -t tcs-garr:latest .
```

### Environment variables

| Name                 | Description                        | Default Value         |
| -------------------- | ---------------------------------- | --------------------- |
| HARICA_USERNAME      | Username for HARICA authentication | None                  |
| HARICA_PASSWORD      | Password for HARICA authentication | None                  |
| HARICA_TOTP_SEED     | TOTP seed for two-factor auth      | None                  |
| HARICA_OUTPUT_FOLDER | Directory for output files         | ~/harica_certificates |

### Run

For the following commands, you can either use the builded image or pull the image from
GitHub container
[registry](https://github.com/ConsortiumGARR/tcs-garr/pkgs/container/tcs-garr).

```bash
docker run --name tcs-garr tcs-garr:latest --version
```

Or a more complex example can be:

```bash
docker run --name tcs-garr \
  -e HARICA_USERNAME=${HARICA_USERNAME} \
  -e HARICA_PASSWORD=${HARICA_PASSWORD} \
  -e HARICA_TOTP_SEED=${HARICA_TOTP_SEED} \
  -e HARICA_OUTPUT_FOLDER=${HARICA_OUTPUT_FOLDER} \
  -v ${HARICA_OUTPUT_FOLDER}:${HARICA_OUTPUT_FOLDER} \
  tcs-garr:latest request --cn <domain> --alt_names <alt_names>
```

The entrypoint is already set to `tcs-garr`, so just add arguments or options.

## License

This project is licensed under the GNU General Public License v3.0. See the [LICENSE](LICENSE.md) file for details.

## Contributing and Further Development

Contributions, further developments, error reports (and possibly fixes) are welcome.

For more info, please read the [CONTRIBUTING](CONTRIBUTING.md) file.
