import logging
import pytest
import lib.commands as commands

vtpm_signing_test_script = """#!/bin/env bash

set -ex

apt-get install -y tpm2-tools > /dev/null

tpm2_selftest --fulltest

tpm2_getrandom 32 > /dev/null

TMPDIR=`mktemp -d`

# Create an Endorsement primary key
tpm2_createprimary --hierarchy e --key-context ${TMPDIR}/primary.ctx > /dev/null

# Create key objects
tpm2_create --key-algorithm rsa --public ${TMPDIR}/rsa.pub --private ${TMPDIR}/rsa.priv --parent-context \
            ${TMPDIR}/primary.ctx > /dev/null

# Load keys into the TPM
tpm2_load --parent-context ${TMPDIR}/primary.ctx --public ${TMPDIR}/rsa.pub --private ${TMPDIR}/rsa.priv \
          --key-context ${TMPDIR}/rsa.ctx > /dev/null

# Delete loaded key files
rm -f ${TMPDIR}/rsa.pub ${TMPDIR}/rsa.priv

# Message to sign
echo 'XCP-ng Rulez' > ${TMPDIR}/message.dat

# Sign the message
tpm2_sign --key-context ${TMPDIR}/rsa.ctx --hash-algorithm sha256 --signature ${TMPDIR}/sig.rssa \
          ${TMPDIR}/message.dat > /dev/null

# Verify signature
tpm2_verifysignature --key-context ${TMPDIR}/rsa.ctx --hash-algorithm sha256 --message ${TMPDIR}/message.dat \
                     --signature ${TMPDIR}/sig.rssa > /dev/null

# Verify with another message
echo "XCP-ng Still Rulez" > ${TMPDIR}/message.dat

# Verify signature !!!!! THIS MUST FAIL !!!!!
if tpm2_verifysignature --key-context ${TMPDIR}/rsa.ctx --hash-algorithm sha256 --message ${TMPDIR}/message.dat \
                        --signature ${TMPDIR}/sig.rssa > /dev/null 2>&1; then
    echo "Should not succeed"
    exit 1
fi

rm -rf ${TMPDIR}
"""

def _vtpm_get_for_vm(host, vm_uuid):
    try:
        res = host.xe('vtpm-list', {'vm': vm_uuid})
        return res.splitlines()[0].split(':')[1].strip()
    except IndexError:
        return None

def _vtpm_create(host, vm_uuid):
    logging.info("Creating vtpm for vm %s" % vm_uuid)
    return host.xe('vtpm-create', {'vm-uuid': vm_uuid})

def _vtpm_destroy(host, vtpm_uuid):
    if vtpm_uuid is None:
        return

    logging.info("Destroying vtpm %s" % vtpm_uuid)
    host.xe('vtpm-destroy', {'uuid': vtpm_uuid}, force=True)

def _vtpm_init(host, uefi_vm):
    vm = uefi_vm

    # vm must be shutdown to attach a vtpm
    if not vm.is_halted():
        force = vm.is_paused() or vm.is_suspended()
        vm.shutdown(verify=True, force=force)

    vtpm_uuid = _vtpm_get_for_vm(host, vm.uuid)
    # Fail if vtpm-destroy fails since it's not possible to attach more than
    # one vtpm to a vm
    _vtpm_destroy(host, vtpm_uuid)

@pytest.mark.small_vm
@pytest.mark.usefixtures("host_at_least_8_3")
def test_vtpm(host, uefi_vm):
    global vtpm_signing_test_script
    vm = uefi_vm
    res = True

    _vtpm_init(host, vm)

    vtpm_uuid = _vtpm_create(host, vm.uuid)

    vm.start()
    # this also tests the guest tools at the same time since they are used
    # for retrieving the IP address and management agent status.
    vm.wait_for_os_booted()

    # Basic TPM2 tests with tpm2-tools
    try:
        logging.info("Running TPM2 test script on the VM")
        out = vm.execute_script(vtpm_signing_test_script)
        logging.info("*****\n%s\n*****" % out)
    except commands.SSHCommandFailed as e:
        logging.error("%s" % str(e))
        res = False

    vm.shutdown(verify=True)

    try:
        _vtpm_destroy(host, vtpm_uuid)
    except Exception:
        logging.warning("Failed to destroy vtpm")

    assert res
