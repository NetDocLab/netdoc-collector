# IPv6 command selection (#253)

The IOS collector requests `show ipv6 interface` once. For the default context it
requests `show ipv6 neighbors`, `show ipv6 route` and `show ipv6 nd on-link prefix`;
named contexts use their `vrf NAME` forms. NX-OS requests Interface, neighbor and
route output with `vrf all` once. The existing raw/parsed transport is unchanged.

Command selection tests exercise the real public plugin interface without device
access. These are documented requests, not proof of command availability, successful
acquisition, permissions or vendor/model/release compatibility. No positive IPv6
device captures are available. IOS ND on-link-cache availability is platform and
release dependent. EOS and generic per-command outcome tracking remain out of scope.

The companion NetDoc backend implements bounded text adapters and both ingestion
paths; its `docs/architecture/ipv6-onlink-implementation.md` records grammar bounds,
source preservation, synthetic validation and remaining native acquisition work.

References:

- [IOS scoped ND](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst3750x_3560x/software/release/15-2_3_e/consolidated_guide/b_1523e_consolidated_3750x_3560X_cg/configuring_ipv6_unicast_routing.html).
- [IOS on-link prefix table](https://www.cisco.com/c/en/us/td/docs/switches/lan/catalyst9400/software/release/26-x/command_reference/b_26x_9400_cr/ip_addressing__services_commands.html).
- [NX-OS Interface and neighbor commands](https://www.cisco.com/c/en/us/td/docs/switches/datacenter/nexus9000/sw/7-x/command_references/show_commands/b_N9K_Show_Commands_703i5x/b_N9K_Show_Commands_703i5x_chapter_01001.html).
