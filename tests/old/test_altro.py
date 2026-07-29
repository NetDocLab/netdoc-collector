def test_scan_host_can_be_called_twice_in_the_same_process(scanner):
    """Regression test for the PluginNameAlreadyRegistered bug (see review)."""
    with (
        patch.object(NetworkScanner, '_check_port', return_value=True),
        patch('netdoc_collector.core.scanner.SSHDetect') as mock_ssh,
        patch('netdoc_collector.core.scanner.InitNornir') as mock_init_nornir,
    ):
        mock_ssh.return_value.autodetect.return_value = 'cisco_ios'
        mock_init_nornir.return_value.run.return_value = _fake_discovery_result('x')

        first = scanner._scan_host('10.0.0.1')
        second = scanner._scan_host('10.0.0.2')  # must not raise PluginNameAlreadyRegistered

    assert first is not None
    assert second is not None
