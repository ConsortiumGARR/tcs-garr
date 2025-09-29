# TCS-GARR Client

![Version](https://img.shields.io/badge/Version-0.25.1-brightgreen.svg)

[![python](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
![Contributions welcome](https://img.shields.io/badge/Contributions-Welcome-brightgreen.svg)

[![PyPI Downloads](https://static.pepy.tech/badge/tcs-garr)](https://pepy.tech/projects/tcs-garr)

## Overview

**TCS-GARR Client** is a CLI tool for interacting with the HARICA platform via its API.

It supports operations such as:

* Listing and downloading certificates
* Requesting and approving certificates
* Managing ACME accounts and domain validations
* Generating domain validation tokens
* Exporting reports and more

## ⚠️ Disclaimer

**Consortium GARR is not affiliated with HARICA, and the present work has not been
endorsed by or agreed with HARICA.**

**Consortium GARR provides this code as-is to the community for sharing purposes but
does not garantee support, maintenance, or further development of the code. Use it at
your own discretion.**

### Prerequisites

Before using the TCS-GARR client, please ensure the following:

1. **Create a local account on the Harica platform**: You must create a local account on
   Harica at [https://cm.harica.gr](https://cm.harica.gr). Do not use federated IDEM/edugain
   credentials, as they do not support API access.

   * If you're already logged in with an academic login, you can create a new local
     account using an email alias. Academic login users do not have a password and
     therefore cannot use the API.

2. **Required Roles and 2FA**: To use specific API commands, your account must have the
   appropriate roles and 2FA enabled where required. Check the [Command Roles and 2FA
   Requirements](#-command-roles-and-2fa-requirements) section for details.

   * **Enable 2FA (Two-Factor Authentication)** on your profile page if you need to
     perform actions such as approving certificates or managing domain validation.

   * If administrative permissions are required (e.g., domain validation), request an
     existing administrator to elevate your account.

> [!CAUTION]
> ⚠️ **Save the TOTP seed** after enabling 2FA, as you will need it for authentication.
> The TOTP seed follows the format `otpauth://totp/HARICA:username@domain.tld?secret=************&issuer=HARICA&digits=6`.

Once these steps are completed, you are ready to use the TCS-GARR client.

> [!IMPORTANT]
> 🕒 The OTP (One-Time Password) is generated based on the date and time of your PC. If
> the client fails to authenticate and returns an "Invalid OTP" error, please ensure that
> your device's date and time are correct and synchronized with a public NTP server.

### 🔐 Command Roles and 2FA Requirements

**USER** is the default role assigned to a logged-in user with no special permissions
and who has not been granted any additional roles by an administrator.

Other roles, apart from **USER**, require 2FA and are provided by an administrator.

| Command  | Role Needed             | 2FA Needed |
| -------- | ----------------------- | ---------- |
| approve  | SSL_ENTERPRISE_APPROVER | ✔️          |
| cancel   | USER                    | ❌          |
| acme     | ENTERPRISE_ADMIN        | ✔️          |
| domains  | ENTERPRISE_ADMIN        | ✔️          |
| download | USER                    | ❌          |
| init     | None                    | ❌          |
| k8s      | None                    | ❌          |
| list     | USER                    | ❌          |
| request  | USER                    | ❌          |
| revoke   | USER                    | ❌          |
| smime    | ENTERPRISE_ADMIN        | ❌          |
| upgrade  | None                    | ❌          |
| validate | ENTERPRISE_ADMIN        | ✔️          |
| whoami   | USER                    | ❌          |

## 🛠 Installation

You can install the TCS-GARR client in a virtual environment using `pip` or via `pipx`.

### Virtual Environment

1. Open a terminal or command prompt and navigate to the directory where you want to
   install the package. Then, run the following command to create a virtual environment:

    ```bash
    mkdir <path>
    python -m venv venv
    ```

    This will create a folder named `venv` in your project directory, containing a
    self-contained Python environment.

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

## ⚙️ Configuration

After installation, the first time you run the client, you will need to initialize the
configuration file with your credentials by running:

```bash
tcs-garr init
```

This will create a `tcs-garr.conf` file in your home directory under `.config/tcs-garr`
path. This file will contain your Harica username, password, TOTP seed, folder for
issued certificates, and HTTP/HTTPS proxy settings (if needed). The file will have
secure permissions.

If a configuration file is not found, the system will notify you to initialize the
configuration using the `tcs-garr init` command.

### Updating Configuration

If you need to update your configuration (including adding or modifying proxy settings),
you can use:

```bash
tcs-garr init --force
```

This will override existing parameters with new values. You can use this command to add
or update HTTP/HTTPS proxy settings.

## 🚀 Usage

Once the setup is complete, you can use the TCS-GARR client for various operations. The
command syntax follows this pattern:

```bash
tcs-garr [command] [options]
```

To see all available commands and options:

```bash
tcs-garr --help

usage: tcs-garr [-h] [--debug] [--version] [--no-check-release] [--environment {production,stg}]
                {acme,approve,cancel,domains,download,init,k8s,list,request,revoke,test,upgrade,validate,whoami} ...

Harica Certificate Manager

positional arguments:
  {acme,approve,cancel,domains,download,init,k8s,list,request,revoke,test,upgrade,validate,whoami}
                        Available commands
    acme                List ACME accounts configured in Harica
    approve             Approve a certificate by ID
    cancel              Cancel a request by ID
    domains             List available domains
    download            Download a certificate by ID
    init                Generate Harica config file
    k8s                 Generate Kubernetes TLS resource file
    list                List and filter certificates
    request             Request a new certificate
    revoke              Revoke a certificate by ID
    smime               Request a new S/MIME certificate
    test                Test Harica API endpoints
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
  -c CONFIG, --config CONFIG
                        Alternative path to the configuration file (note: this will override the default path and will not use environment variables)
```

### Production and staging environments

All commands are executed on the production environment of Harica at
[https://cm.harica.gr](https://cm.harica.gr). By using the `--environment stg` flag, you
can execute commands for the staging environment at
[https://cm-stg.harica.gr](https://cm-stg.harica.gr).

For example, if you want to use the staging environment, you can initialize the
configuration file using the following command:

```bash
tcs-garr --environment stg init
```

### 🔧 Available Commands

1. **Initialize configuration**:

   ```bash
   tcs-garr init
   ```

   This command initializes the configuration file by prompting for your credentials
   (email, password, TOTP seed, output folder, optional proxy, and optional webhook
   settings).

   #### Webhook

   The webhook feature allows you to send notifications to external services (e.g.
   Slack) whenever a new certificate is requested.

      Currently, two webhook types are supported:

      * **slack**: sends a formatted message to a Slack channel.
      * **generic**: sends a `POST` request with a JSON payload containing:

         ```json
         {
            "id": certificate_id,
            "username": requestor
         }
         ```

   To update an existing configuration or add proxy/webhook settings:

   ```bash
   tcs-garr init --force
   ```

2. **Get user profile**:

   ```bash
   tcs-garr whoami
   ```

   This command retrieves the profile of the logged-in user.

3. **List all certificates**:

   The `list` command allows you to generate detailed reports of SSL certificates from
   the Harica service. It supports various filtering options and output formats to help
   you manage your certificates effectively.

   ```bash
   tcs-garr list --help

   usage: tcs-garr list [-h] [--expired-since EXPIRED_SINCE] [--expiring-in EXPIRING_IN] [--status {Valid,Revoked,Expired,Pending,Ready,Completed,Cancelled,All}] [--user [USER]] [--fqdn FQDN]
                        [--full] [--export [EXPORT]] [--json [JSON]] [--type {ACME,API}] [--acme-account-id ACME_ACCOUNT_ID]

   options:
   -h, --help            show this help message and exit
   --expired-since EXPIRED_SINCE
                           List certificates whose expiry date is X days before now.
   --expiring-in EXPIRING_IN
                           List certificates whose expiry date is X days after now.
   --status {Valid,Revoked,Expired,Pending,Ready,Completed,Cancelled,All}
                           Filter certificates by status. Default is valid.
   --user [USER]         Filter certificates owner by user. Without arg (--user only) will filter for the logged in user. Use this if you have Approver role or Admin role.
   --fqdn FQDN           Filter certificates by a substring in their Fully Qualified Domain Name (FQDN).
   --full                Retrieve full certificate information.
   --export [EXPORT]     Export certificates to json file. Without arg uses default file, with arg specifies output file (e.g. --export output.json).
   --json [JSON]         Alias for --export. Export certificates to json file.
   --type {ACME,API}     Filter certificates by type.
   --acme-account-id ACME_ACCOUNT_ID   Filter certificates by acme account id.
   ```

   This command will list all available certificates, included ACME ones. You can filter
   them by date range using the `--expired-since`, `--expiring-in` or `--fqdn` options.

   By default, the command displays certificate information in a tabular format, showing
   certificate ID, common name, expiration date, status, information, alternative names,
   requestor and type (if requested via API or ACME) . When using the `--export` or
   `--json` option without a filename, the information is displayed in JSON format on
   the terminal and saved to the default file. With a filename specified, the data is
   saved to that file without terminal output.

   #### Important Note on `--full` Option

   The extended information provided by `--full` includes certificate metadata such as
   issuer details, certificate content, key usage, and other technical parameters from
   the certification authority.

   When using the `--full` flag, be aware of the following:

   1. **Performance Impact**: This option significantly increases processing time as it
      requires an additional API request for each certificate in the result set. For
      large certificate lists, this operation can take several minutes to complete.

   2. **Rate Limiting**: The Harica platform implements rate limiting on API requests.
      Using `--full` with a large number of certificates may trigger rate limiting
      responses, especially when running multiple commands in quick succession.

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

   Replace `ID` with the ID of the certificate you wish to download. You can use
   `pemBundle` or `certificate` as arguments for specific download formats.

   The `download` command allows you to download certificates requested via API or ACME.

5. **Request a new certificate**:

   ```bash
   tcs-garr request --help

   usage: tcs-garr request [-h] [--profile {OV,DV}] [--wait] [--disable-webhook] (--csr CSR | --cn CN) [--alt_names ALT_NAMES]

   options:
   -h, --help            show this help message and exit
   --profile {OV,DV}     Profile to use between OV or DV. Default: OV
   --wait                Wait for the certificate to be approved
   --disable-webhook     Disable calling webhook after submit request. This works only if webhook_url has been configured
   --csr CSR             Path to an existing CSR file.
   --cn CN               Common name of the certificate.
   --alt_names ALT_NAMES
                           Comma-separated alternative names (only used with --cn).
   ```

   The `request` command is used to submit a new certificate request to Harica via API.

   You can either provide an existing Certificate Signing Request (`--csr`) or specify
   the details for generating a new CSR, including the Common Name (`--cn`) and any
   Subject Alternative Names (`--alt_names`). If a new CSR is created using the `--cn`
   and `--alt_names` options, a private key will also be automatically generated.

   You can choose between the `OV` (OV Profile) or `DV` (DV Profile) profile using the
   `--profile` option. Default is `OV`.

   After submitting the certificate request, the request must be approved by another
   Administrator before the certificate can be downloaded. Ensure that an administrator
   is available to review and approve your request.

   With `--wait`` flag, the command will wait for the certificate to be approved by
   another administrator. When approved, it will be automatically downloaded.

   If Webhook URL has been configured (see `init` command), the webhook will be called
   after the certificate is requested to Harica. If `--disable-webhook` is set, the
   webhook will not be called. Webhook feature can be used to send notification to
   external service like Slack to inform channel or group when a new certificate has been
   requested.

6. **Approve a certificate**:

   ```bash
   usage: tcs-garr approve [-h] (--id ID | --list-pending | --all)

   options:
   -h, --help      show this help message and exit
   --id ID         ID of the certificates (comma separated) to approve.
   --list-pending  List all pending requests.
   --all           Approve all pending requests.
   ```

   You can list all pending requests using the `--list-pending` option or approve all
   pending requests using the `--all` option.

   You can also approve a specific certificate by providing its ID using the `--id`
   option.

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

   This command generates validation tokens for the specified domains. Replace `DOMAINS`
   with a comma-separated list of domains you need to validate.

   To get the list of all available domains in your organization, use the `domains`
   command.

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

   This command is used to generate a Kubernetes secret YAML file for storing a TLS
   certificate and its associated private key. The resulting secret can be used in
   Kubernetes clusters to securely store TLS certificates for applications requiring
   encrypted communication.

   The command requires the paths to both the certificate file (--cert) and the private
   key file (--key), as well as the target Kubernetes namespace (--namespace) where the
   secret will be created.

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

11. **Revoke certificate**:

   ```bash
   usage: tcs-garr revoke [-h] --id ID

   options:
   -h, --help  show this help message and exit
   --id ID     ID of the certificate to revoke.
   ```

   Only certificates requested via API can be revoked. ACME certificates cannot be
   revoked via this client.

12. **Acme accounts**:

   ```bash
   usage: tcs-garr acme [-h] {list,info,create,disable,domains} ...

   positional arguments:
   {list,info,create,disable,domains}
      list                List all ACME accounts
      info                Get information on a specific ACME account including secrets
      create              Create a new ACME account
      disable             Disable an ACME account
      domains             Perform actions on ACME account domains and rules

   options:
   -h, --help            show this help message and exit
   ```

   This command allows you to manage ACME accounts, including listing all accounts,
   getting information on a specific account, creating new accounts, and performing
   actions on ACME account domains and rules. You can use the `list`, `info`, `create`,
   `disable` and `domains` subcommands to perform these actions. Check `help` for each
   subcommand for more details.

13. **Issue S/MIME Certificates**:

   ```bash
   usage: main.py smime [-h] [--profile {SV,MV}] [--disable-webhook] (--csr CSR | --emails EMAILS) [--gn GN] [--sn SN] [--output-filename OUTPUT_FILENAME] [--force] [--download-type {pemBundle,certificate}]

   options:
     -h, --help            show this help message and exit
     --profile {SV,MV}     Profile to use between SV or MV. Default: SV
     --disable-webhook     Disable calling webhook after submit request. This works only if webhook_url has been configured
     --csr CSR             Path to an existing CSR file.
     --emails EMAILS       Comma-separated email addresses of the certificate (up to three).
     --gn GN               Given Name of the Subject (only used with --email).
     --sn SN               Surname of the Subject (only used with --email).
     --output-filename OUTPUT_FILENAME
                           Optional filename to save the certificate inside the default output folder.
     --force, -f           Force overwrite if the output file already exists.
     --download-type {pemBundle,certificate}
                           Type of download: 'pemBundle' or 'certificate'. Default is 'pemBundle'.
   ```

   This command allows the user to generate a Certificate Signing Request (CSR)
   or provide an existing CSR to request a new S/MIME certificate from the
   Harica service. The user can choose between different certificate profiles
   (MV, SV). If `MV` (Mailbox Validated, i.e. "Email only") is chosen, the
   surname and given name attributes must not be provided. For `SV` (Sponsor
   Validated, i.e. "OV and IV") surname and given name are required.
   Certificates are returned immediately, without the need for manual approval.

14. **Test apis**:

   ```bash
   usage: tcs-garr test [-h] --endpoint ENDPOINT [--data DATA] [--foutput FOUTPUT]

   options:
   -h, --help           show this help message and exit
   --endpoint ENDPOINT  Endpoint to test
   --data DATA          Data to send with the request in JSON format (e.g. '--data {"id": "f3b2a6a8-5da6-46f1-8f1d-3f9d2a6f32ec"}')
   --foutput FOUTPUT    File to output JSON response (e.g. --foutput test.json)
   ```

   This command allows you to test Harica API endpoints. You can use the `--endpoint`
   option to specify the endpoint you want to test. You can also use the `--data` option
   to send data with the request in JSON format. Finally, you can use the `--foutput`
   option to save the JSON response to a file.

## 🐳 Docker

Docker image is available at GitHub container
[registry](https://github.com/ConsortiumGARR/tcs-garr/pkgs/container/tcs-garr). You can
pull them via:

```bash
docker pull ghcr.io/consortiumgarr/tcs-garr:<your_desired_version>
```

### 📦 Build

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
| HARICA_HTTP_PROXY    | HTTP Proxy                         | None                  |
| HARICA_HTTPS_PROXY   | HTTPS Proxy                        | None                  |
| WEBHOOK_URL          | Webhook URL                        | None                  |
| WEBHOOK_TYPE         | Webhook Type                       | Slack                 |

Info about
[webhook](https://github.com/ConsortiumGARR/tcs-garr?tab=readme-ov-file#webhook)
environment variable.

### ▶ Run

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
  -e HARICA_HTTP_PROXY=${HARICA_HTTP_PROXY} \
  -e HARICA_HTTPS_PROXY=${HARICA_HTTPS_PROXY} \
  -e HARICA_WEBHOOK_URL=${HARICA_WEBHOOK_URL} \
  -v ${HARICA_OUTPUT_FOLDER}:${HARICA_OUTPUT_FOLDER} \
  tcs-garr:latest request --cn <domain> --alt_names <alt_names>
```

The entrypoint is already set to `tcs-garr`, so just add arguments or options.

### Docker compose

Check the [docker-compose](docker-compose.yml) file for more details.

## Contributors

We would like to thank all the contributors to this project:

* [uedvt359](https://github.com/uedvt359)
* [kaidohTips](https://github.com/kaidohTips)

## License

This project is licensed under the GNU General Public License v3.0. See the
[LICENSE](LICENSE.md) file for details.

## Contributing and Further Development

Contributions, further developments, error reports (and possibly fixes) are welcome.

For more info, please read the [CONTRIBUTING](CONTRIBUTING.md) file.
