import logging
import pytest

#vtpm_uuid = None

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
    if vm.is_running():
        vm.shutdown(verify=True)

    # Will fail if vtpm-destroy fails since it's not possible to attach more
    # than 1 vtpm to a vm
    _vtpm_destroy(host, _vtpm_get_for_vm(host, vm.uuid))

def test_vtpm(host, uefi_vm):
    vm = uefi_vm
    res = True

    _vtpm_init(host, vm)

    vtpm_uuid = _vtpm_create(host, vm.uuid)
    # ~ vtpm_uuid = _vtpm_get_for_vm(host, vm.uuid)

    vm.start()
    # this also tests the guest tools at the same time since they are used
    # for retrieving the IP address and management agent status.
    vm.wait_for_os_booted()

    # Basic TPM2 tests with tpm2-tools
    try:
        logging.info("Installing tpm2-tools package")
        vm.ssh(['apt-get', 'install', '-y', 'tpm2-tools'])
        
        logging.info("Running 'tpm2_selftest --fulltest'")
        vm.ssh(['tpm2_selftest', '--fulltest'])

        logging.info("Running 'tpm2_getrandom --hex 32'")
        vm.ssh(['tpm2_getrandom', '--hex', '32'])
    except:
        logging.error("tpm2 test failed")
        res = False

    vm.shutdown(verify=True)

    try:
        _vtpm_destroy(host, vtpm_uuid)
    except:
        logging.warning("Failed to destroy vtpm")

    assert res
