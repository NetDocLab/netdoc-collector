class TestScan:
    def test_scan_aggregates_results_and_survives_exceptions(self, scanner):
        scanner.networks = [ipaddress.IPv4Network('10.0.0.0/30')]  # 2 usable hosts

        def fake_scan_host(ip):
            if ip.endswith('.1'):
                raise RuntimeError('simulated netmiko crash')
            return HostResult(ip=ip, netdoc_plugin='netmiko:cisco:ios:ssh')

        with patch.object(NetworkScanner, '_scan_host', side_effect=fake_scan_host):
            results = scanner.scan()

        assert len(results) == 1  # the exception must not abort the whole scan
