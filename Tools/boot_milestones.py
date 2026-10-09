"""Evidence stages only: restore userland is not an iOS desktop boot."""
import re


def inspect(serial, trace):
    returns = re.findall(r"Exception return from AArch64 EL1 to AArch64 EL0 PC (0x[0-9a-fA-F]+)", trace)
    launchd = any("com.apple.xpc.launchd|" in line and "<Notice>: hello" in line
                  for line in serial.splitlines())
    return {"userland_execution_confirmed": bool(returns) and launchd,
            "el0_return_count": len(returns), "first_el0_pc": returns[0] if returns else None,
            "launchd_hello_seen": launchd,
            "restore_environment_seen": launchd and "<Notice>: Restore environment starting." in serial,
            "early_boot_complete_seen": launchd and "<Notice>: Early boot complete." in serial,
            "nvram_service_wait_seen": "IOResourceMatch = IONVRAM;" in serial,
            "springboard_confirmed": False, "booted_ios": False}
