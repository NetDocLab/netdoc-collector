"""Base plugin definitions and common utilities for NetDoc plugins.

This module defines the abstract :class:`BasePlugin` class and shared helpers
used by all vendor-specific collector plugins.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException
from netmiko.utilities import get_structured_data
from nornir.core.exceptions import NornirSubTaskError
from nornir.core.task import MultiResult, Task
from nornir_netmiko.tasks import netmiko_send_command
from textfsm.parser import TextFSMError

logger = logging.getLogger(__name__)


class BasePlugin(ABC):
    """Abstract base class for a NetDoc vendor/platform plugin."""

    def __init__(
        self,
        host_name: str,
        host_data: dict,
        report_path: Path | None,
        cmd_timeout: int = 240,
    ):
        """Initialize the plugin with host context and output options.

        Args:
            host_name (str): Nornir host name used as the output key.
            host_data (dict): host inventory metadata including plugin mapping.
            report_path (Path | None): optional directory for debug output files.
            cmd_timeout (int): per-command timeout in seconds.
        """
        self.report_path = None
        self.host_name: str = host_name
        self.host_data: dict = host_data
        self.cmd_timeout: int = cmd_timeout

        if report_path:
            # Save report path to save logs locally
            self.report_path = report_path / Path(host_name)
            self.report_path.mkdir(exist_ok=True, parents=True)

    @staticmethod
    def parse_netmiko_output(raw_text, platform, cmd) -> None | list:
        """Parse raw Netmiko command output to structured data.

        Args:
            raw_output (str): raw device output from Netmiko.
            platform (str): Netmiko platform name used for parsing.
            cmd (str): command string to identify the parser template.

        Returns:
            None | list: parsed output list, or None when parsing is unavailable.
        """
        try:
            parsed_text: list = get_structured_data(raw_text, platform=platform, command=cmd)
            if isinstance(parsed_text, list):
                # Valid output is a list
                return parsed_text
        except TextFSMError:
            pass
        if 'vrf' in cmd:
            logging.warning(f"Cannot parse command '{cmd}'")
        return None

    @staticmethod
    def slugify(text: str) -> str:
        """Normalize text into a slug suitable for filenames."""
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[\s_-]+', '-', text)
        text = re.sub(r'^-+|-+$', '', text)
        return text

    @abstractmethod
    def collect(self, task: Task) -> dict[str, Any]:
        """Collect data from devices and return result in NetDoc format."""
        ...

    def run_netmiko_cmd(self, task: Task, platform, cmd) -> tuple[str, None | list]:
        """Execute a Netmiko command and optionally parse the result.

        Args:
            task (Task): Nornir task context used to run the command.
            platform (str): Netmiko platform used to parse the output.
            cmd (str): command string to execute on the device.

        Returns:
            tuple[str, None | list]: raw output and parsed structured output.
        """
        logger.info(f"Running netmiko command '{cmd}' on {self.host_name}")

        try:
            # Get or open Netmiko connection
            net_connect = task.host.get_connection('netmiko', task.nornir.config)

            # Privilege escalation only if required
            if net_connect.secret and not net_connect.check_enable_mode():
                logger.info(f'Entering enable mode on {self.host_name}')
                net_connect.enable()

        except Exception as e:
            logger.error(f'Failed to enter enable mode on {self.host_name}: {e}')
            raise

        try:
            cmd_result: MultiResult = task.run(
                task=netmiko_send_command,
                command_string=cmd,
                use_timing=False,
                read_timeout=self.cmd_timeout,
                use_textfsm=False,
            )
            logger.debug(f"Raw output for command '{cmd}' on {self.host_name}: {cmd_result.result}")
        except NornirSubTaskError as e:
            inner = e.result.exception
            if isinstance(inner, NetmikoAuthenticationException):
                logger.error(f'Authentication failed on {self.host_name}')
            elif isinstance(inner, NetmikoTimeoutException):
                logger.error(f"Timeout on {self.host_name} running '{cmd}'")
            else:
                logger.error(f"Error running command '{cmd}' on {self.host_name}: {inner}")
            raise

        # Dump output files
        raw_text = cmd_result.result
        parsed_text = self.parse_netmiko_output(raw_text, platform, cmd)
        self.write_output(raw_text, cmd)
        self.write_output(parsed_text, cmd)

        return raw_text, parsed_text

    def write_output(self, content, log) -> None:
        """Write raw or structured command output to the report path.

        Args:
            content (str | dict | list): raw or parsed command output.
            log (str): command name or log label used to build the filename.
        """
        if not self.report_path:
            # Write output if report path is set only
            return
        if not content:
            # Skipping empty content
            return

        log_file = self.slugify(log)
        if isinstance(content, dict | list):
            # Write a JSON file
            with open(self.report_path / Path(f'{log_file}.json'), 'w', encoding='utf-8') as fh:
                json.dump(content, fh, indent=2)
            return

        # Write a raw content
        with open(self.report_path / Path(f'{log_file}.raw'), 'w') as fh:
            fh.write(content)
