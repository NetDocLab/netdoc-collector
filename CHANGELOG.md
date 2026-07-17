# Changelog

## [0.6.4](https://github.com/NetDocLab/netdoc-collector/compare/v0.6.3...v0.6.4) (2026-07-13)


### Bug Fixes

* add show interface status on nxos ([2c43bfb](https://github.com/NetDocLab/netdoc-collector/commit/2c43bfb62d1d5c91cedf44edc16328cd752b55b3))
* add show stp summary on nexus ([f9bcfbb](https://github.com/NetDocLab/netdoc-collector/commit/f9bcfbb0aaa1e216b7e2c068db0624b11013e5e7))

## [0.6.3](https://github.com/NetDocLab/netdoc-collector/compare/v0.6.2...v0.6.3) (2026-07-10)


### Bug Fixes

* support insecure certificates ([9bb8afb](https://github.com/NetDocLab/netdoc-collector/commit/9bb8afb0f735378417c0f9c9b1e6b37d231c5dd5))
* support insecure certificates ([b8be945](https://github.com/NetDocLab/netdoc-collector/commit/b8be94583cc1b57d9015c6fa68a50dd13f6b3fe9))

## [0.6.2](https://github.com/NetDocLab/netdoc-collector/compare/v0.6.1...v0.6.2) (2026-07-10)


### Bug Fixes

* add additional commands ([3b59277](https://github.com/NetDocLab/netdoc-collector/commit/3b5927769ae5d312305323a5d771559a3f9a5567))
* force paramiko 4 for legacy devices ([f751903](https://github.com/NetDocLab/netdoc-collector/commit/f7519038b4a926c39f89ae26b91cec1921546656))

## [0.6.1](https://github.com/NetDocLab/netdoc-collector/compare/v0.6.0...v0.6.1) (2026-07-08)


### Bug Fixes

* consolidate nxos command ([2a8b22d](https://github.com/NetDocLab/netdoc-collector/commit/2a8b22da1cd2d341c9676be2ded7ebaa3c066397))
* fix race, improve ipaddress exception ([8192418](https://github.com/NetDocLab/netdoc-collector/commit/8192418eca46e2d2420c18f112c767f21a16680d))
* improve slugify, add tests ([fe9a43b](https://github.com/NetDocLab/netdoc-collector/commit/fe9a43bbc96b7b7cc154091f084759a9e2281db9))
* update SDK and NX-OS collector and tests ([158a491](https://github.com/NetDocLab/netdoc-collector/commit/158a4916e6b7e8d30b2aede115d58a1c3140c9a3))

## [0.6.0](https://github.com/NetDocLab/netdoc-collector/compare/v0.5.0...v0.6.0) (2026-07-05)


### Bug Fixes

* improve ci/cd ([2706e42](https://github.com/NetDocLab/netdoc-collector/commit/2706e42d8674dfc59c9fc8df9b172a7802ee9d0f))
* linting and docs ([0126784](https://github.com/NetDocLab/netdoc-collector/commit/012678447ab50ac7946852fbc8b2df2ce4edc6ab))
* update SDK ([50a9ffe](https://github.com/NetDocLab/netdoc-collector/commit/50a9ffe8905635e0108ece6d28af25948e4bc674))
* upload logs (main and tasks) ([22af749](https://github.com/NetDocLab/netdoc-collector/commit/22af7490df227aed158c45ec578fbe779897ab07))
* upload logs per each task ([6816be5](https://github.com/NetDocLab/netdoc-collector/commit/6816be53fb0f1561ce0d8fefe192ee02e2ac6e90))

## [0.5.0](https://github.com/NetDocLab/netdoc-collector/compare/v0.4.3...v0.5.0) (2026-06-20)


### Bug Fixes

* decrease coverage ([49cf304](https://github.com/NetDocLab/netdoc-collector/commit/49cf304f1054e8df667b175936dbf5acdaa22f31))
* decrease coverage level to run the workflow ([4d518ca](https://github.com/NetDocLab/netdoc-collector/commit/4d518ca73cbe69a44fe65dc1aafcc63b403451ce))
* fix ci tests ([a318d67](https://github.com/NetDocLab/netdoc-collector/commit/a318d67f0deafa9ccb34bb5a26531e196359aca1))
* update cryptography==48.0.1 ([2fbfa1b](https://github.com/NetDocLab/netdoc-collector/commit/2fbfa1b9ad0fd88bead375bb79389e4cdf201eb4))
* update poetry.lock ([b67e948](https://github.com/NetDocLab/netdoc-collector/commit/b67e948797d12441c91319034f511ea45727b3fd))

## [0.4.3](https://github.com/NetDocLab/netdoc-collector/compare/v0.4.2...v0.4.3) (2026-06-12)


### Bug Fixes

* fix privilege escalation ([de1964e](https://github.com/NetDocLab/netdoc-collector/commit/de1964e6f3d8e0f487c688fd91eca9021f4659ac))
* fix upload payload ([4d4d7d7](https://github.com/NetDocLab/netdoc-collector/commit/4d4d7d77f080da2e5ef16b14300f97a251ce0a39))
* fix upload payload ([db31485](https://github.com/NetDocLab/netdoc-collector/commit/db31485e26ae94b720b17ac5da703f9d6f636f01))

## [0.4.2](https://github.com/NetDocLab/netdoc-collector/compare/v0.4.1...v0.4.2) (2026-06-10)


### Bug Fixes

* add log after upload has been completed ([0decfa5](https://github.com/NetDocLab/netdoc-collector/commit/0decfa5c62240d825b38320b0ca078b5abde7a16))
* fix main and base to upload parsed log ([55ced21](https://github.com/NetDocLab/netdoc-collector/commit/55ced2138995690a68154cf823c4baa8d1889358))
* fix upload function ([b5670a2](https://github.com/NetDocLab/netdoc-collector/commit/b5670a201fa4b88056ea1dbc4801f500ed52702d))
* update plugins to send parsed output ([501162b](https://github.com/NetDocLab/netdoc-collector/commit/501162bb2ce72f7a7af5a1aa970e1109fcf2a923))
* upload parsed_output to backend ([67148c6](https://github.com/NetDocLab/netdoc-collector/commit/67148c69d1e93e5a20b6bc09b448f13856790ec4))

## [0.4.1](https://github.com/NetDocLab/netdoc-collector/compare/v0.4.0...v0.4.1) (2026-06-09)


### Bug Fixes

* improve scanner performance and logging ([f658d4b](https://github.com/NetDocLab/netdoc-collector/commit/f658d4ba5bd3194a671293394ead0900c12ae49e))
* trigger exit on heartbeat task ([6899897](https://github.com/NetDocLab/netdoc-collector/commit/6899897dda0400cdbf4b9076092530b16794e992))
* update sdk ([f428aab](https://github.com/NetDocLab/netdoc-collector/commit/f428aab8d7f3e182bd11f063177c315c9ce8f3b5))
* update sdk functions ([66d5f49](https://github.com/NetDocLab/netdoc-collector/commit/66d5f49040449859f4db6d6bd124de486dcd45d9))

## [0.4.0](https://github.com/NetDocLab/netdoc-collector/compare/v0.3.0...v0.4.0) (2026-06-07)


### Bug Fixes

* adjust SDK for managed mode ([f164947](https://github.com/NetDocLab/netdoc-collector/commit/f1649473e6a395213b964acbb600745f38f79147))
* fix plugins ([633e112](https://github.com/NetDocLab/netdoc-collector/commit/633e112115cbe073f2ccb17836df4f4b8766e0b4))


### Documentation

* update doc ([2a8f88f](https://github.com/NetDocLab/netdoc-collector/commit/2a8f88f79879aa26b9f550e227a5cee12a34358c))
* update readme ([5c73de0](https://github.com/NetDocLab/netdoc-collector/commit/5c73de046fa89a6d84f8a9e76566141d629c2983))

## [0.3.0](https://github.com/NetDocLab/netdoc-collector/compare/v0.2.2...v0.3.0) (2026-06-05)


### Bug Fixes

* fix scanner ([4a78050](https://github.com/NetDocLab/netdoc-collector/commit/4a78050e321cf586c294dc0fb612e6845c46ab19))
* json linting ([724fa23](https://github.com/NetDocLab/netdoc-collector/commit/724fa23cc06c233ecd96cc7597a0f28d5145eb8c))

## [0.2.2](https://github.com/NetDocLab/netdoc-collector/compare/v0.2.1...v0.2.2) (2026-05-26)


### Bug Fixes

* environment ([dbaac12](https://github.com/NetDocLab/netdoc-collector/commit/dbaac129c8923fc2a379c5de8e36f53e42879233))
* linting ([2a3a93b](https://github.com/NetDocLab/netdoc-collector/commit/2a3a93bc895f2f4284739544e075d64a72aeedcd))
