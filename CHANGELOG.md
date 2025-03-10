## 0.16.24-rc.1 (2025-03-10)

## 0.16.24-rc.0 (2025-03-10)

### Fix

- k8s secret yaml formatting. add file name and secret name as optional

## 0.16.23 (2025-03-07)

### Fix

- Add chain folder as resource

## 0.16.22 (2025-03-07)

### Fix

- Autocomple chain if trust intermediate not present

## 0.16.22-rc.0 (2025-02-28)

### Fix

- Fix SAN order

## 0.16.21 (2025-02-28)

### Fix

- Separete pypi and test.pypi

## 0.16.20 (2025-02-28)

## 0.16.20-rc.0 (2025-02-28)

### Fix

- Add test pypi for release candidate

## 0.16.19 (2025-02-28)

### Fix

- check pipeline release

## 0.16.18 (2025-02-28)

### Fix

- backward compatibility config file permissions

## 0.16.17 (2025-02-28)

### Fix

- specify only python version. create user home dir.

## 0.16.16 (2025-02-28)

### Fix

- Fix pipeline

## 0.16.15 (2025-02-28)

### Fix

- recheck pipeline

## 0.16.14 (2025-02-28)

### Fix

- recheck pipeline

## 0.16.13 (2025-02-28)

### Fix

- retry pipeline

## 0.16.12 (2025-02-28)

### Fix

- check pipeline

## 0.16.11 (2025-02-28)

### Fix

- Check pipeline

## 0.16.10 (2025-02-28)

### Fix

- ci pipeline

## 0.16.9 (2025-02-27)

### Fix

- release

## 0.16.8 (2025-02-27)

### Fix

- check pipeline

## 0.16.7 (2025-02-27)

### Fix

- Check pipeline

## 0.16.6 (2025-02-27)

### Fix

- Fix pipeline

## 0.16.5 (2025-02-27)

### Fix

- Fix pipeline

## 0.16.4 (2025-02-27)

### Fix

- Fix pipeline

## 0.16.3 (2025-02-27)

### Fix

- Check pipeline

## 0.16.2 (2025-02-27)

### Fix

- Increase verbosity of whoami command

## 0.16.1 (2025-02-27)

### Fix

- Add check for new release on execution

## 0.16.0 (2025-02-27)

### Feat

- github action that create release

## 0.15.2 (2025-02-26)

### Fix

- Add wait flag to request command

## 0.15.1 (2025-02-26)

### Fix

- Bump cryptography packages to 43.0.1 https://openssl-library.org/news/secadv/20240903.txt

## 0.15.0 (2025-02-26)

### Feat

- github action

## 0.14.0 (2025-02-26)

### Feat

- Add multiple environment (production, stg)

### Refactor

- Move commands to classes

## 0.13.1 (2025-02-25)

### Fix

- add missing library

## 0.13.0 (2025-02-25)

### Feat

- Add self upgrade command

## 0.12.0 (2025-02-25)

### Feat

- ability to generate k8s tls resource

### Fix

- docker chown workdir

## 0.11.0 (2025-02-24)

### Feat

- Add request of DV certificate

## 0.10.1 (2025-02-21)

### Fix

- change api endpoint for pending certs.

## 0.10.0 (2025-02-21)

### Feat

- raise custom exception if downloading a pending cert

## 0.9.0 (2025-02-21)

### Feat

- save certificate id

## 0.8.0 (2025-02-21)

### Feat

- add dir to gitignore

## 0.7.1 (2025-02-21)

### Fix

- Fix cn and alt_names order
- Fix list certificate with filters expired-since and expiring-in

## 0.7.0 (2025-02-21)

### Feat

- workaround for merge request pipelines
- add show version cli flag
- load config from env variable. validate configs. fix path expansion. Use constant for paths
- ruff update

## 0.6.0 (2025-02-21)

### Feat

- docker ci rules
- tcs doker

### Fix

- use grep and sed to extract version

## 0.5.2 (2025-02-20)

### Fix

- Improve message exception when user is not admin or approver

## 0.5.1 (2025-02-19)

### Fix

- Fix parameters for request certificate.

## 0.5.0 (2025-02-18)

### Feat

- Submit request from existing CSR file

## 0.4.0 (2025-02-10)

### Feat

- Add cancel request

## 0.3.0 (2025-02-10)

### Feat

- List and approve all pending certificate request

## 0.2.7 (2025-02-05)

### Fix

- Fix docstring

## 0.2.6 (2025-02-04)

### Fix

- poetry config file
- gitlab-ci
- gitlab-ci

### Refactor

- Add commitizen for conventional commit and semantic release

## 0.2.5 (2025-02-03)

## 0.2.4 (2025-02-03)

### Refactor

- Change name to tcs-garr
